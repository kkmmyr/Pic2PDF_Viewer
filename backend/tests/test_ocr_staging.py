from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from services.novel_db.connection import with_db
from services.novel_db.extractor import OcrPageResult
from services.novel_db.migrations import upgrade_head
from services.novel_db.ocr_staging import (
    collect_input_pages,
    prepare_run,
    publish_run,
    save_page_result,
)


@pytest.fixture
def staged_book(tmp_data_dir) -> tuple[str, list]:
    upgrade_head()
    book_name = "surya-test-book"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    Image.new("RGB", (100, 140), "white").save(images_dir / "001.png")
    Image.new("RGB", (100, 140), "white").save(images_dir / "002.png")
    return book_name, collect_input_pages(book_name)


def _passed_page(page_no: int, image_sha256: str, text: str) -> OcrPageResult:
    return {
        "page_no": page_no,
        "image_sha256": image_sha256,
        "state": "passed",
        "full_text": text,
        "char_count": len(text),
        "raw_output": f'<div data-label="Text" data-bbox="0 0 1000 1000">{text}</div>',
        "block_count": 1,
        "quality_flags": [],
        "ink_coverage": 1.0,
        "attempt_count": 1,
        "error_message": None,
    }


def test_run_resumes_passed_page_and_publishes_only_when_complete(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, tasks = prepare_run(book_name, "surya2", "model-sha", input_pages)
    assert [task["page_no"] for task in tasks] == [1, 2]

    save_page_result(run_id, _passed_page(1, input_pages[0].image_sha256, "一頁目"))
    with pytest.raises(ValueError, match="incomplete"):
        publish_run(run_id, input_pages)

    with with_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0

    resumed_run_id, remaining = prepare_run(book_name, "surya2", "model-sha", input_pages)
    assert resumed_run_id == run_id
    assert [task["page_no"] for task in remaining] == [2]

    save_page_result(run_id, _passed_page(2, input_pages[1].image_sha256, "二頁目"))
    publish_run(run_id, input_pages)

    with with_db() as conn:
        book = conn.execute("SELECT id, page_count, ocr_done_at FROM books WHERE name=?", (book_name,)).fetchone()
        assert (book[1], book[2] is not None) == (2, True)
        pages = conn.execute(
            "SELECT page_no, full_text FROM pages WHERE book_id=? ORDER BY page_no", (book[0],)
        ).fetchall()
        assert [(row[0], row[1]) for row in pages] == [(1, "一頁目"), (2, "二頁目")]
        assert conn.execute("SELECT state FROM ocr_runs WHERE id=?", (run_id,)).fetchone()[0] == "completed"


def test_publish_rejects_source_image_changed_after_ocr(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "本文"))

    Image.new("RGB", (100, 140), "black").save(input_pages[0].image_path)

    with pytest.raises(ValueError, match="source image changed"):
        publish_run(run_id, input_pages)

    with with_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
