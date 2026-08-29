from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from PIL import Image

from services.novel_db import ocr_publication_history, ocr_qa_publication
from services.novel_db import ocr_qa as qa_facade
from services.novel_db import ocr_staging as staging_facade
from services.novel_db.connection import with_db
from services.novel_db.extractor import OcrPageResult
from services.novel_db.migrations import upgrade_head
from services.novel_db.ocr_page_classification import classify_run_pages
from services.novel_db.ocr_provenance import candidate_manifest
from services.novel_db.ocr_publication_history import activate_published_run
from services.novel_db.ocr_qa_publication import approve_and_publish_run
from services.novel_db.ocr_qa_queries import get_qa_image_path, get_qa_run, list_qa_runs
from services.novel_db.ocr_qa_review import review_qa_page
from services.novel_db.ocr_qa_staging import stage_run_for_qa
from services.novel_db.ocr_run_store import collect_input_pages, prepare_run, save_page_result


def _unique_content(length: int, *, start: int = 0) -> str:
    return "".join(chr(0x4E00 + start + index) for index in range(length))


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
        "selection_reason": None,
    }


def test_qa_detail_exposes_candidate_selection_reason(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "qwen35_dots_review_v1", "composite", input_pages)
    for page in input_pages:
        result = _passed_page(page.page_no, page.image_sha256, "本文")
        result["selection_reason"] = "dots_materially_more_complete"
        save_page_result(run_id, result)
    stage_run_for_qa(run_id, input_pages)

    detail = get_qa_run(run_id)

    assert detail["pages"][0]["selection_reason"] == "dots_materially_more_complete"


def _prepare_approved_run(staged_book, *, text_prefix: str = "新本文") -> tuple[int, str]:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(
            run_id,
            _passed_page(page.page_no, page.image_sha256, f"{text_prefix}{page.page_no}"),
        )
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
    return run_id, book_name


def _seed_existing_canonical(book_name: str) -> int:
    with with_db() as conn:
        cursor = conn.execute(
            "INSERT INTO books "
            "(name, pdf_path, images_dir, page_count, indexed_at, ocr_done_at) "
            "VALUES (?, '', 'old-images', 2, 'old-index', 'old-ocr')",
            (book_name,),
        )
        book_id = int(cursor.lastrowid)
        conn.executemany(
            "INSERT INTO pages "
            "(book_id, page_no, image_path, full_text, char_count, page_type, index_eligible) "
            "VALUES (?, ?, '', ?, ?, 'narrative', 1)",
            [
                (book_id, 1, "旧本文一", 4),
                (book_id, 2, "旧本文二", 4),
            ],
        )
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
        conn.commit()
    return book_id


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
        index_state = conn.execute(
            "SELECT source_revision, status FROM novel_search_index_state WHERE index_name='page_icu'"
        ).fetchone()
        assert tuple(index_state) == (1, "stale")


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


def test_existing_publication_failure_preserves_canonical_fts_and_history(staged_book) -> None:
    run_id, book_name = _prepare_approved_run(staged_book)
    book_id = _seed_existing_canonical(book_name)
    with with_db() as conn:
        conn.execute(
            "CREATE TRIGGER fail_versioned_publication BEFORE INSERT ON ocr_publications "
            "WHEN NEW.action='publish' BEGIN SELECT RAISE(ABORT, 'forced versioned publication failure'); END"
        )
        conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced versioned publication failure"):
        approve_and_publish_run(run_id, "tester")

    with with_db() as conn:
        book = conn.execute(
            "SELECT images_dir, page_count, indexed_at, ocr_done_at FROM books WHERE id=?",
            (book_id,),
        ).fetchone()
        pages = conn.execute(
            "SELECT page_no, full_text FROM pages WHERE book_id=? ORDER BY page_no",
            (book_id,),
        ).fetchall()
        fts_texts = conn.execute("SELECT full_text FROM pages_fts ORDER BY rowid").fetchall()
        publications = conn.execute("SELECT COUNT(*) FROM ocr_publications").fetchone()[0]
        legacy_runs = conn.execute("SELECT COUNT(*) FROM ocr_runs WHERE engine='legacy'").fetchone()[0]
        run = conn.execute(
            "SELECT state, qa_state FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
    assert tuple(book) == ("old-images", 2, "old-index", "old-ocr")
    assert [tuple(row) for row in pages] == [(1, "旧本文一"), (2, "旧本文二")]
    assert [row[0] for row in fts_texts] == ["旧本文一", "旧本文二"]
    assert publications == 0
    assert legacy_runs == 0
    assert tuple(run) == ("awaiting_qa", "pending")


def test_rollback_failure_preserves_current_pages_fts_and_active_publication(staged_book) -> None:
    run_id, book_name = _prepare_approved_run(staged_book)
    book_id = _seed_existing_canonical(book_name)
    approve_and_publish_run(run_id, "tester")
    with with_db() as conn:
        publications = conn.execute(
            "SELECT id, run_id, action, retired_at FROM ocr_publications WHERE book_id=? ORDER BY id",
            (book_id,),
        ).fetchall()
        legacy_run_id = int(publications[0][1])
        active_publication_id = int(publications[1][0])
        ocr_done_at_before = conn.execute(
            "SELECT ocr_done_at FROM books WHERE id=?",
            (book_id,),
        ).fetchone()[0]
        conn.execute(
            "CREATE TRIGGER fail_rollback_publication BEFORE INSERT ON ocr_publications "
            "WHEN NEW.action='rollback' BEGIN SELECT RAISE(ABORT, 'forced rollback failure'); END"
        )
        conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced rollback failure"):
        activate_published_run(legacy_run_id, "tester", "failure injection")

    with with_db() as conn:
        pages = conn.execute(
            "SELECT page_no, full_text FROM pages WHERE book_id=? ORDER BY page_no",
            (book_id,),
        ).fetchall()
        fts_texts = conn.execute("SELECT full_text FROM pages_fts ORDER BY rowid").fetchall()
        active = conn.execute(
            "SELECT id, run_id, action FROM ocr_publications WHERE book_id=? AND retired_at IS NULL",
            (book_id,),
        ).fetchone()
        publication_count = conn.execute(
            "SELECT COUNT(*) FROM ocr_publications WHERE book_id=?",
            (book_id,),
        ).fetchone()[0]
        ocr_done_at_after = conn.execute(
            "SELECT ocr_done_at FROM books WHERE id=?",
            (book_id,),
        ).fetchone()[0]
    assert [tuple(row) for row in pages] == [(1, "新本文1"), (2, "新本文2")]
    assert [row[0] for row in fts_texts] == ["新本文1", "新本文2"]
    assert tuple(active) == (active_publication_id, run_id, "publish")
    assert publication_count == 2
    assert ocr_done_at_after == ocr_done_at_before


def test_successful_run_cannot_be_approved_twice(staged_book) -> None:
    run_id, _ = _prepare_approved_run(staged_book)
    approve_and_publish_run(run_id, "tester")

    with pytest.raises(ValueError, match="not awaiting QA"):
        approve_and_publish_run(run_id, "tester")

    with with_db() as conn:
        publications = conn.execute("SELECT action FROM ocr_publications ORDER BY id").fetchall()
        active_count = conn.execute("SELECT COUNT(*) FROM ocr_publications WHERE retired_at IS NULL").fetchone()[0]
    assert [row[0] for row in publications] == ["publish"]
    assert active_count == 1


def test_concurrent_run_approval_creates_one_publication(staged_book, monkeypatch) -> None:
    run_id, _ = _prepare_approved_run(staged_book)
    barrier = Barrier(2)
    original_publish_rows = ocr_qa_publication._publish_rows

    def publish_after_both_validated(*args, **kwargs) -> None:
        barrier.wait(timeout=5)
        original_publish_rows(*args, **kwargs)

    monkeypatch.setattr(ocr_qa_publication, "_publish_rows", publish_after_both_validated)

    def approve() -> Exception | None:
        try:
            ocr_qa_publication.approve_and_publish_run(run_id, "tester")
        except Exception as error:
            return error
        return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        errors = list(executor.map(lambda _: approve(), range(2)))

    failures = [error for error in errors if error is not None]
    assert len(failures) == 1
    assert isinstance(failures[0], ValueError)
    assert str(failures[0]) == "OCR run is not awaiting QA"
    with with_db() as conn:
        publications = conn.execute("SELECT action FROM ocr_publications ORDER BY id").fetchall()
        run = conn.execute("SELECT state, qa_state FROM ocr_runs WHERE id=?", (run_id,)).fetchone()
    assert [row[0] for row in publications] == ["publish"]
    assert tuple(run) == ("completed", "approved")


def test_publication_creates_verified_pre_transaction_backup(staged_book, tmp_data_dir) -> None:
    run_id, _ = _prepare_approved_run(staged_book)

    approve_and_publish_run(run_id, "tester", "operator note")

    backup_root = Path(tmp_data_dir["NOVEL_DB_DIR"]).parent / "ocr-publication-backups"
    generations = [path for path in backup_root.iterdir() if path.is_dir()]
    assert len(generations) == 1
    generation = generations[0]
    manifest = json.loads((generation / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["operation"] == "publish"
    assert manifest["run_id"] == run_id
    assert manifest["integrity_check"] == "ok"
    assert manifest["bytes"] == (generation / "novel.db").stat().st_size
    assert len(manifest["sha256"]) == 64
    with sqlite3.connect(generation / "novel.db") as restored:
        restored_run = restored.execute(
            "SELECT state, qa_state FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        restored_publications = restored.execute("SELECT COUNT(*) FROM ocr_publications").fetchone()[0]
    assert restored_run == ("awaiting_qa", "pending")
    assert restored_publications == 0
    with with_db() as conn:
        note = conn.execute(
            "SELECT note FROM ocr_publications WHERE run_id=? AND retired_at IS NULL",
            (run_id,),
        ).fetchone()[0]
    assert note == f"operator note; verified backup={generation}"


def test_publication_backup_failure_preserves_canonical_state(staged_book, monkeypatch) -> None:
    run_id, book_name = _prepare_approved_run(staged_book)
    book_id = _seed_existing_canonical(book_name)

    def fail_backup(*_args, **_kwargs) -> str:
        raise OSError("forced publication backup failure")

    monkeypatch.setattr(ocr_qa_publication, "create_verified_publication_backup", fail_backup)
    with pytest.raises(OSError, match="forced publication backup failure"):
        approve_and_publish_run(run_id, "tester")

    with with_db() as conn:
        book = conn.execute(
            "SELECT images_dir, page_count, indexed_at, ocr_done_at FROM books WHERE id=?",
            (book_id,),
        ).fetchone()
        pages = conn.execute(
            "SELECT page_no, full_text FROM pages WHERE book_id=? ORDER BY page_no",
            (book_id,),
        ).fetchall()
        fts_texts = conn.execute("SELECT full_text FROM pages_fts ORDER BY rowid").fetchall()
        publications = conn.execute("SELECT COUNT(*) FROM ocr_publications").fetchone()[0]
        run = conn.execute("SELECT state, qa_state FROM ocr_runs WHERE id=?", (run_id,)).fetchone()
    assert tuple(book) == ("old-images", 2, "old-index", "old-ocr")
    assert [tuple(row) for row in pages] == [(1, "旧本文一"), (2, "旧本文二")]
    assert [row[0] for row in fts_texts] == ["旧本文一", "旧本文二"]
    assert publications == 0
    assert tuple(run) == ("awaiting_qa", "pending")


def test_rollback_backup_failure_keeps_active_publication(staged_book, monkeypatch) -> None:
    run_id, book_name = _prepare_approved_run(staged_book)
    book_id = _seed_existing_canonical(book_name)
    approve_and_publish_run(run_id, "tester")
    with with_db() as conn:
        publications = conn.execute(
            "SELECT id, run_id FROM ocr_publications WHERE book_id=? ORDER BY id",
            (book_id,),
        ).fetchall()
        legacy_run_id = int(publications[0][1])
        active_publication_id = int(publications[1][0])

    def fail_backup(*_args, **_kwargs) -> str:
        raise OSError("forced rollback backup failure")

    monkeypatch.setattr(ocr_publication_history, "create_verified_publication_backup", fail_backup)
    with pytest.raises(OSError, match="forced rollback backup failure"):
        activate_published_run(legacy_run_id, "tester")

    with with_db() as conn:
        pages = conn.execute(
            "SELECT page_no, full_text FROM pages WHERE book_id=? ORDER BY page_no",
            (book_id,),
        ).fetchall()
        active = conn.execute(
            "SELECT id, run_id FROM ocr_publications WHERE book_id=? AND retired_at IS NULL",
            (book_id,),
        ).fetchone()
    assert [tuple(row) for row in pages] == [(1, "新本文1"), (2, "新本文2")]
    assert tuple(active) == (active_publication_id, run_id)


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
            "VALUES (?, ?, '', ?, ?, ?, ?)",
            [
                (book_id, 1, "旧本文一", 4, "narrative", 1),
                (book_id, 2, "旧奥付本文", 5, "colophon_or_ad", 0),
                (book_id, 3, "削除対象本文", 6, "narrative", 1),
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
        publications = conn.execute(
            "SELECT run_id, action, retired_at FROM ocr_publications WHERE book_id=? ORDER BY id",
            (book_id,),
        ).fetchall()
    assert [tuple(row) for row in pages] == [(1, "外部採用本文"), (2, "補正採用本文")]
    assert [row[0] for row in fts_texts] == ["外部採用本文", "補正採用本文"]
    assert [(row[1], row[2] is None) for row in publications] == [
        ("legacy_snapshot", False),
        ("publish", True),
    ]

    legacy_run_id = int(publications[0][0])
    activate_published_run(legacy_run_id, "tester", "rollback test")

    with with_db() as conn:
        restored = conn.execute(
            "SELECT page_no, full_text, page_type, index_eligible FROM pages WHERE book_id=? ORDER BY page_no",
            (book_id,),
        ).fetchall()
        active = conn.execute(
            "SELECT run_id, action FROM ocr_publications WHERE book_id=? AND retired_at IS NULL",
            (book_id,),
        ).fetchone()
        legacy_materialized = conn.execute(
            "SELECT page_no, published_text FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (legacy_run_id,),
        ).fetchall()
    assert [tuple(row) for row in restored] == [
        (1, "旧本文一", "narrative", 1),
        (2, "旧奥付本文", "colophon_or_ad", 0),
    ]
    assert tuple(active) == (legacy_run_id, "rollback")
    assert [tuple(row) for row in legacy_materialized] == [(1, "旧本文一"), (2, "旧奥付本文")]


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


def test_stage_requires_every_page_including_excluded_sample_pages(tmp_data_dir) -> None:
    upgrade_head()
    book_name = "sample-boundary-qa"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    for page_no in range(1, 17):
        Image.new("RGB", (100, 140), "white").save(images_dir / f"{page_no:03d}.png")
    input_pages = collect_input_pages(book_name)
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        text = _unique_content(400)
        if page.page_no == 12:
            text = "別作品 電子特別お試し版"
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, text))

    stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        required = conn.execute(
            "SELECT page_no FROM ocr_page_results WHERE run_id=? AND qa_state='required' ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [row[0] for row in required] == list(range(1, 17))


def test_run_rejects_unversioned_model(staged_book) -> None:
    book_name, input_pages = staged_book

    with pytest.raises(ValueError, match="model revision"):
        prepare_run(book_name, "surya2", "unversioned", input_pages)


def test_page_preserves_runtime_candidates_and_phase_timing(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    primary_text = "主候補"
    external_text = "外部候補"
    primary_raw = "<primary>"
    external_raw = "<external>"
    page = _passed_page(1, input_pages[0].image_sha256, external_text)
    page.update(
        {
            "primary_text": primary_text,
            "external_text": external_text,
            "primary_raw_output": primary_raw,
            "external_raw_output": external_raw,
            "selected_engine": "external",
            "candidate_manifest": candidate_manifest(
                primary_text=primary_text,
                primary_raw_output=primary_raw,
                primary_state="passed",
                primary_block_count=1,
                primary_quality_flags=[],
                primary_attempt_count=1,
                external_text=external_text,
                external_raw_output=external_raw,
                external_state="passed",
                external_block_count=2,
                external_quality_flags=["yomitoku_adjudication"],
                external_attempt_count=2,
            ),
            "processing_timing": {
                "image_read_ms": 4,
                "primary_ocr_ms": 120,
                "external_ocr_ms": 44,
                "selection_ms": 2,
                "total_ms": 170,
            },
            "runtime_manifest": {
                "schema_version": 1,
                "engine": "surya2",
                "model_revision": "model-sha",
                "platform": "Windows-test",
            },
            "run_timing": {"worker_init_ms": 500},
        }
    )

    save_page_result(run_id, page)

    with with_db() as conn:
        run = conn.execute(
            "SELECT runtime_manifest_json, timing_json FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        saved = conn.execute(
            "SELECT primary_text, external_text, primary_raw_output, external_raw_output, "
            "candidate_manifest_json, processing_timing_json FROM ocr_page_results "
            "WHERE run_id=? AND page_no=1",
            (run_id,),
        ).fetchone()

    assert '"model_revision":"model-sha"' in run[0]
    assert run[1] == '{"worker_init_ms":500}'
    assert tuple(saved[:4]) == (primary_text, external_text, primary_raw, external_raw)
    assert '"text_sha256"' in saved[4]
    assert saved[5] == ('{"external_ocr_ms":44,"image_read_ms":4,"primary_ocr_ms":120,"selection_ms":2,"total_ms":170}')


def test_page_preserves_empty_primary_candidate_when_external_is_selected(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    external_text = "外部候補"
    primary_raw = "<empty-primary>"
    external_raw = "<external>"
    page = _passed_page(1, input_pages[0].image_sha256, external_text)
    page.update(
        {
            "primary_text": "",
            "external_text": external_text,
            "primary_raw_output": primary_raw,
            "external_raw_output": external_raw,
            "selected_engine": "external",
            "candidate_manifest": candidate_manifest(
                primary_text="",
                primary_raw_output=primary_raw,
                primary_state="passed",
                primary_block_count=0,
                primary_quality_flags=[],
                primary_attempt_count=1,
                external_text=external_text,
                external_raw_output=external_raw,
                external_state="passed",
                external_block_count=1,
                external_quality_flags=["yomitoku_adjudication"],
                external_attempt_count=2,
            ),
        }
    )

    save_page_result(run_id, page)

    with with_db() as conn:
        saved = conn.execute(
            "SELECT primary_text, external_text, selected_engine FROM ocr_page_results WHERE run_id=? AND page_no=1",
            (run_id,),
        ).fetchone()

    assert tuple(saved) == ("", external_text, "external")


def test_page_rejects_changed_runtime_manifest_and_candidate_sha(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    first = _passed_page(1, input_pages[0].image_sha256, "本文1")
    first["runtime_manifest"] = {
        "schema_version": 1,
        "engine": "surya2",
        "model_revision": "model-sha",
        "platform": "Windows",
    }
    save_page_result(run_id, first)

    second = _passed_page(2, input_pages[1].image_sha256, "本文2")
    second["runtime_manifest"] = {
        "schema_version": 1,
        "engine": "surya2",
        "model_revision": "model-sha",
        "platform": "macOS",
    }
    with pytest.raises(ValueError, match="changed within"):
        save_page_result(run_id, second)

    tampered = _passed_page(2, input_pages[1].image_sha256, "本文2")
    manifest = candidate_manifest(
        primary_text="本文2",
        primary_raw_output=tampered["raw_output"],
        primary_state="passed",
        primary_block_count=1,
        primary_quality_flags=[],
        primary_attempt_count=1,
        external_text=None,
        external_raw_output=None,
        external_state=None,
        external_block_count=None,
        external_quality_flags=None,
        external_attempt_count=None,
    )
    manifest["primary"]["text_sha256"] = "0" * 64
    tampered["candidate_manifest"] = manifest
    with pytest.raises(ValueError, match="primary candidate text_sha256 mismatch"):
        save_page_result(run_id, tampered)


def test_qa_persists_review_and_correction_timing(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, f"本文{page.page_no}"))
    stage_run_for_qa(run_id, input_pages)

    review_qa_page(
        run_id,
        1,
        "approved",
        None,
        "narrative",
        "normal_prose",
        "codex",
        "補正文",
        "2026-08-29T10:00:00.000Z",
        12_345,
        4_321,
    )
    detail = get_qa_run(run_id)

    assert detail["ocr_finished_at"] is not None
    assert detail["qa_started_at"] is not None
    assert detail["qa_finished_at"] is None
    assert detail["pages"][0]["review_started_at"] == "2026-08-29T10:00:00.000Z"
    assert detail["pages"][0]["review_duration_ms"] == 12_345
    assert detail["pages"][0]["correction_duration_ms"] == 4_321

    with pytest.raises(ValueError, match="non-negative"):
        review_qa_page(
            run_id,
            2,
            "approved",
            None,
            "narrative",
            "normal_prose",
            "primary",
            None,
            "2026-08-29T10:00:00Z",
            -1,
            None,
        )
