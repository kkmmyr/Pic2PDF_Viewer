from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from services.novel_db import ocr_qa as qa_facade
from services.novel_db import ocr_staging as staging_facade
from services.novel_db.connection import with_db
from services.novel_db.extractor import OcrPageResult
from services.novel_db.migrations import upgrade_head
from services.novel_db.ocr_page_classification import classify_run_pages
from services.novel_db.ocr_qa_publication import approve_and_publish_run
from services.novel_db.ocr_qa_queries import get_qa_image_path, get_qa_run, list_qa_runs
from services.novel_db.ocr_qa_review import review_qa_page
from services.novel_db.ocr_qa_staging import stage_run_for_qa
from services.novel_db.ocr_run_store import collect_input_pages, prepare_run, save_page_result


def test_facade_preserves_public_symbol_identity() -> None:
    assert staging_facade.collect_input_pages is collect_input_pages
    assert staging_facade.prepare_run is prepare_run
    assert staging_facade.save_page_result is save_page_result
    assert staging_facade.classify_run_pages is classify_run_pages
    assert staging_facade.stage_run_for_qa is stage_run_for_qa
    assert staging_facade.review_qa_page is review_qa_page
    assert staging_facade.approve_and_publish_run is approve_and_publish_run
    assert staging_facade.get_qa_image_path is get_qa_image_path
    assert staging_facade.get_qa_run is get_qa_run
    assert staging_facade.list_qa_runs is list_qa_runs
    assert qa_facade.stage_run_for_qa is stage_run_for_qa
    assert qa_facade.review_qa_page is review_qa_page
    assert qa_facade.approve_and_publish_run is approve_and_publish_run
    assert qa_facade.get_qa_image_path is get_qa_image_path
    assert qa_facade.get_qa_run is get_qa_run
    assert qa_facade.list_qa_runs is list_qa_runs


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
        "layout_type": "normal_prose",
        "primary_text": text,
        "external_text": None,
        "selected_engine": "primary",
    }


def test_run_resumes_then_requires_qa_before_publication(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, tasks = prepare_run(book_name, "surya2", "model-sha", input_pages)
    assert [task["page_no"] for task in tasks] == [1, 2]

    save_page_result(run_id, _passed_page(1, input_pages[0].image_sha256, "一頁目"))
    with pytest.raises(ValueError, match="incomplete"):
        stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0

    resumed_run_id, remaining = prepare_run(book_name, "surya2", "model-sha", input_pages)
    assert resumed_run_id == run_id
    assert [task["page_no"] for task in remaining] == [2]

    save_page_result(run_id, _passed_page(2, input_pages[1].image_sha256, "二頁目"))
    stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
        assert conn.execute("SELECT state FROM ocr_runs WHERE id=?", (run_id,)).fetchone()[0] == "awaiting_qa"
        required = conn.execute(
            "SELECT page_no FROM ocr_page_results WHERE run_id=? AND qa_state='required' ORDER BY page_no",
            (run_id,),
        ).fetchall()
        assert [row[0] for row in required] == [1, 2]

    review_qa_page(run_id, 1, "approved", None, "narrative", "normal_prose", "primary", None)
    review_qa_page(
        run_id,
        2,
        "approved",
        "確認済み",
        "narrative",
        "normal_prose",
        "primary",
        None,
    )
    approve_and_publish_run(run_id, "tester")

    with with_db() as conn:
        book = conn.execute("SELECT id, page_count, ocr_done_at FROM books WHERE name=?", (book_name,)).fetchone()
        assert (book[1], book[2] is not None) == (2, True)
        pages = conn.execute(
            "SELECT page_no, full_text, page_type, index_eligible FROM pages WHERE book_id=? ORDER BY page_no",
            (book[0],),
        ).fetchall()
        assert [tuple(row) for row in pages] == [
            (1, "一頁目", "narrative", 1),
            (2, "二頁目", "narrative", 1),
        ]
        run = conn.execute("SELECT state, qa_state, qa_reviewer FROM ocr_runs WHERE id=?", (run_id,)).fetchone()
        assert tuple(run) == ("completed", "approved", "tester")


def test_stage_rejects_source_image_changed_after_ocr(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "本文"))

    Image.new("RGB", (100, 140), "black").save(input_pages[0].image_path)

    with pytest.raises(ValueError, match="source image changed"):
        stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0


def test_run_approval_rejects_unreviewed_required_pages(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "本文"))
    stage_run_for_qa(run_id, input_pages)

    with pytest.raises(ValueError, match="required QA pages remain"):
        approve_and_publish_run(run_id, "tester")


def test_run_approval_rejects_rejected_pages(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "本文"))
    stage_run_for_qa(run_id, input_pages)
    review_qa_page(run_id, 1, "rejected", "再確認", "narrative", "normal_prose", "primary", None)
    review_qa_page(run_id, 2, "approved", None, "narrative", "normal_prose", "primary", None)

    with pytest.raises(ValueError, match="rejected QA pages remain"):
        approve_and_publish_run(run_id, "tester")


@pytest.mark.parametrize(
    ("column", "message"),
    [
        ("page_type", "unclassified OCR pages remain"),
        ("layout_type", "unclassified OCR layouts remain"),
    ],
)
def test_run_approval_rejects_unclassified_results(staged_book, column: str, message: str) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "本文"))
    stage_run_for_qa(run_id, input_pages)
    for page in input_pages:
        review_qa_page(
            run_id,
            page.page_no,
            "approved",
            None,
            "narrative",
            "normal_prose",
            "primary",
            None,
        )
    with with_db() as conn:
        conn.execute(
            f"UPDATE ocr_page_results SET {column}='unknown' WHERE run_id=? AND page_no=1",
            (run_id,),
        )
        conn.commit()

    with pytest.raises(ValueError, match=message):
        approve_and_publish_run(run_id, "tester")


def test_publication_rolls_back_book_pages_fts_and_run_state(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "本文"))
    stage_run_for_qa(run_id, input_pages)
    for page in input_pages:
        review_qa_page(
            run_id,
            page.page_no,
            "approved",
            None,
            "narrative",
            "normal_prose",
            "primary",
            None,
        )
    with with_db() as conn:
        conn.execute(
            "CREATE TRIGGER fail_ocr_run_completion BEFORE UPDATE OF state ON ocr_runs "
            "WHEN NEW.state='completed' BEGIN SELECT RAISE(ABORT, 'forced publication failure'); END"
        )
        conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced publication failure"):
        approve_and_publish_run(run_id, "tester")

    with with_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM pages_fts").fetchone()[0] == 0
        run = conn.execute("SELECT state, qa_state FROM ocr_runs WHERE id=?", (run_id,)).fetchone()
    assert tuple(run) == ("awaiting_qa", "pending")


def test_publication_uses_reviewed_text_deletes_stale_pages_and_rebuilds_fts(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    first = _passed_page(1, input_pages[0].image_sha256, "主系候補本文")
    first["external_text"] = "外部採用本文"
    save_page_result(run_id, first)
    save_page_result(run_id, _passed_page(2, input_pages[1].image_sha256, "補正前本文"))
    stage_run_for_qa(run_id, input_pages)
    review_qa_page(run_id, 1, "approved", None, "narrative", "normal_prose", "external", None)
    review_qa_page(run_id, 2, "approved", None, "narrative", "normal_prose", "codex", "補正採用本文")
    with with_db() as conn:
        cursor = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count) VALUES (?, '', 'old', 3)",
            (book_name,),
        )
        book_id = int(cursor.lastrowid)
        conn.executemany(
            "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count, page_type, index_eligible) "
            "VALUES (?, ?, '', ?, ?, 'narrative', 1)",
            [
                (book_id, 1, "旧本文一", 4),
                (book_id, 2, "旧本文二", 4),
                (book_id, 3, "削除対象本文", 6),
            ],
        )
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
        conn.commit()

    approve_and_publish_run(run_id, "tester")

    with with_db() as conn:
        pages = conn.execute(
            "SELECT page_no, full_text FROM pages WHERE book_id=? ORDER BY page_no",
            (book_id,),
        ).fetchall()
        fts_texts = conn.execute("SELECT full_text FROM pages_fts ORDER BY rowid").fetchall()
    assert [tuple(row) for row in pages] == [(1, "外部採用本文"), (2, "補正採用本文")]
    assert [row[0] for row in fts_texts] == ["外部採用本文", "補正採用本文"]


def test_page_approval_requires_classification(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "章題のような曖昧な文字列です"))
    stage_run_for_qa(run_id, input_pages)
    with with_db() as conn:
        conn.execute(
            "UPDATE ocr_page_results SET page_type='unknown', index_eligible=0 WHERE run_id=? AND page_no=1",
            (run_id,),
        )
        conn.commit()

    with pytest.raises(ValueError, match="classified"):
        review_qa_page(run_id, 1, "approved", None, "unknown", "normal_prose", "primary", None)


def test_classify_run_pages_is_conservative(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    save_page_result(run_id, _passed_page(1, input_pages[0].image_sha256, "目次\n第一章\n第二章"))
    long_text = "これは物語本文の文章です。" * 40
    save_page_result(run_id, _passed_page(2, input_pages[1].image_sha256, long_text))

    counts = classify_run_pages(run_id)
    assert counts["toc"] == 1
    assert counts["narrative"] == 1
    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no, layout_type FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [tuple(row) for row in rows] == [(1, "structured"), (2, "normal_prose")]


def test_classify_run_pages_excludes_appended_sample(tmp_data_dir) -> None:
    upgrade_head()
    book_name = "sample-boundary"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    for page_no in range(1, 17):
        Image.new("RGB", (100, 140), "white").save(images_dir / f"{page_no:03d}.png")
    input_pages = collect_input_pages(book_name)
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)

    for page in input_pages:
        text = "これは物語本文として十分な長さを持つ文章です。" * 20
        if page.page_no == 12:
            text = "別作品 電子特別お試し版"
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, text))

    counts = classify_run_pages(run_id)

    assert counts["colophon_or_ad"] == 5
    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no, page_type, index_eligible, quality_flags_json "
            "FROM ocr_page_results WHERE run_id=? AND page_no>=11 ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [tuple(row[:3]) for row in rows] == [
        (11, "narrative", 1),
        (12, "colophon_or_ad", 0),
        (13, "colophon_or_ad", 0),
        (14, "colophon_or_ad", 0),
        (15, "colophon_or_ad", 0),
        (16, "colophon_or_ad", 0),
    ]
    assert "sample_content_boundary" in rows[1][3]
    assert all("sample_content_excluded" in row[3] for row in rows[2:])


def test_stage_requires_sample_boundary_but_not_every_excluded_page(tmp_data_dir) -> None:
    upgrade_head()
    book_name = "sample-boundary-qa"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    for page_no in range(1, 17):
        Image.new("RGB", (100, 140), "white").save(images_dir / f"{page_no:03d}.png")
    input_pages = collect_input_pages(book_name)
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        text = "これは物語本文として十分な長さを持つ文章です。" * 20
        if page.page_no == 12:
            text = "別作品 電子特別お試し版"
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, text))

    stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        required = conn.execute(
            "SELECT page_no FROM ocr_page_results WHERE run_id=? AND qa_state='required' ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [row[0] for row in required] == [1, 2, 3, 4, 5, 6, 7, 8, 12, 16]
