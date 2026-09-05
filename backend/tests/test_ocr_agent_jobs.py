from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from services.novel_db import ocr_agent_jobs
from services.novel_db.connection import with_db
from services.novel_db.migrations import upgrade_head

_MODEL_REVISION = "surya2-test-v1"


@pytest.fixture
def agent_job(tmp_data_dir, monkeypatch) -> tuple[int, str, list[Path]]:
    upgrade_head()
    monkeypatch.setattr("config.app_settings.OCR_AGENT_ENABLED", True)
    monkeypatch.setattr("config.app_settings.OCR_ENGINE", "surya2")
    monkeypatch.setattr("config.app_settings.OCR_AGENT_HEARTBEAT_TIMEOUT_SEC", 300)
    book_name = "ocr-agent-book"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    paths = [images_dir / "001.png", images_dir / "002.png"]
    Image.new("RGB", (100, 140), "white").save(paths[0])
    Image.new("RGB", (100, 140), "black").save(paths[1])
    with with_db() as conn:
        cursor = conn.execute(
            "INSERT INTO rebuild_jobs (job_type, target_id, mode, state, enqueued_at) "
            "VALUES ('book', ?, 'ocr', 'queued', datetime('now', '+9 hours'))",
            (book_name,),
        )
        conn.commit()
    return int(cursor.lastrowid), book_name, paths


def _page(page_no: int, path: Path) -> dict:
    image_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    text = f"本文{page_no}"
    return {
        "runtime_manifest": {"schema_version": 1, "engine": "surya2", "model_revision": _MODEL_REVISION},
        "page_no": page_no,
        "image_sha256": image_sha256,
        "state": "passed",
        "full_text": text,
        "char_count": len(text),
        "raw_output": "",
        "block_count": 1,
        "quality_flags": [],
        "ink_coverage": 1.0,
        "attempt_count": 1,
        "server_generation": 1,
        "error_message": None,
    }


def test_agent_claim_submit_complete_stages_qa(agent_job) -> None:
    job_id, book_name, paths = agent_job

    job = ocr_agent_jobs.claim("windows-ocr-1", _MODEL_REVISION)

    assert job is not None
    assert job["id"] == job_id
    assert [task["page_no"] for task in job["books"][0]["tasks"]] == [1, 2]
    assert ocr_agent_jobs.image_path(job_id, "windows-ocr-1", book_name, 1) == paths[0]

    for page_no, path in enumerate(paths, start=1):
        response = ocr_agent_jobs.submit_page(
            job_id,
            "windows-ocr-1",
            book_name,
            _page(page_no, path),
        )
        assert response["status"] == "passed"

    completed = ocr_agent_jobs.complete(job_id, "windows-ocr-1")
    assert completed == {"job_id": job_id, "status": "completed", "books": 1}
    with with_db() as conn:
        job_row = conn.execute(
            "SELECT state, current_step FROM rebuild_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        run_row = conn.execute(
            "SELECT state, qa_state FROM ocr_runs "
            "JOIN ocr_agent_job_runs ON ocr_agent_job_runs.run_id=ocr_runs.id "
            "WHERE ocr_agent_job_runs.job_id=?",
            (job_id,),
        ).fetchone()
        assert tuple(job_row) == ("completed", "awaiting_qa")
        assert tuple(run_row) == ("awaiting_qa", "pending")
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0


def test_agent_reclaim_returns_same_job_and_rejects_wrong_owner(agent_job) -> None:
    job_id, book_name, _ = agent_job
    first = ocr_agent_jobs.claim("windows-ocr-1", _MODEL_REVISION)
    second = ocr_agent_jobs.claim("windows-ocr-1", _MODEL_REVISION)

    assert first is not None and second is not None
    assert first["id"] == second["id"] == job_id
    with pytest.raises(ValueError, match="claim"):
        ocr_agent_jobs.image_path(job_id, "windows-ocr-2", book_name, 1)


def test_agent_rejects_page_hash_mismatch(agent_job) -> None:
    job_id, book_name, paths = agent_job
    ocr_agent_jobs.claim("windows-ocr-1", _MODEL_REVISION)
    page = _page(1, paths[0])
    page["image_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="SHA-256"):
        ocr_agent_jobs.submit_page(job_id, "windows-ocr-1", book_name, page)


def test_agent_heartbeat_timeout_fails_staging_without_touching_canonical(agent_job) -> None:
    job_id, book_name, _ = agent_job
    claimed = ocr_agent_jobs.claim("windows-ocr-1", _MODEL_REVISION)
    assert claimed is not None
    run_id = int(claimed["books"][0]["run_id"])
    with with_db() as conn:
        cursor = conn.execute(
            "INSERT INTO books "
            "(name, pdf_path, images_dir, page_count, indexed_at, ocr_done_at) "
            "VALUES (?, '', 'canonical-images', 1, 'canonical-index', 'canonical-ocr')",
            (book_name,),
        )
        book_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO pages "
            "(book_id, page_no, image_path, full_text, char_count, page_type, index_eligible) "
            "VALUES (?, 1, '', '公開済み本文', 6, 'narrative', 1)",
            (book_id,),
        )
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
        publication_run = conn.execute(
            "INSERT INTO ocr_runs "
            "(book_name, engine, model, source_page_count, state, qa_state) "
            "VALUES (?, 'legacy', 'canonical', 1, 'completed', 'approved')",
            (book_name,),
        )
        publication_run_id = int(publication_run.lastrowid)
        active_publication = conn.execute(
            "INSERT INTO ocr_publications "
            "(book_id, run_id, action, actor, published_at) "
            "VALUES (?, ?, 'legacy_snapshot', 'fixture', 'canonical-published')",
            (book_id, publication_run_id),
        )
        active_publication_id = int(active_publication.lastrowid)
        conn.execute(
            "UPDATE rebuild_jobs SET heartbeat_at='2000-01-01 00:00:00' WHERE id=?",
            (job_id,),
        )
        conn.commit()

    assert ocr_agent_jobs.claim("windows-ocr-2", _MODEL_REVISION) is None

    with with_db() as conn:
        job = conn.execute(
            "SELECT state, error_message FROM rebuild_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        run = conn.execute(
            "SELECT state, error_message FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        book = conn.execute(
            "SELECT images_dir, page_count, indexed_at, ocr_done_at FROM books WHERE id=?",
            (book_id,),
        ).fetchone()
        pages = conn.execute(
            "SELECT page_no, full_text FROM pages WHERE book_id=?",
            (book_id,),
        ).fetchall()
        fts_texts = conn.execute("SELECT full_text FROM pages_fts").fetchall()
        active = conn.execute(
            "SELECT id, run_id, action, retired_at FROM ocr_publications WHERE book_id=? AND retired_at IS NULL",
            (book_id,),
        ).fetchone()
    assert tuple(job) == ("failed", "OCR agent heartbeat timeout")
    assert tuple(run) == ("failed", "OCR agent heartbeat timeout")
    assert tuple(book) == ("canonical-images", 1, "canonical-index", "canonical-ocr")
    assert [tuple(row) for row in pages] == [(1, "公開済み本文")]
    assert [row[0] for row in fts_texts] == ["公開済み本文"]
    assert tuple(active) == (
        active_publication_id,
        publication_run_id,
        "legacy_snapshot",
        None,
    )
