from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from services.novel_db import ocr_agent_jobs
from services.novel_db.connection import with_db
from services.novel_db.migrations import upgrade_head


@pytest.fixture
def agent_job(tmp_data_dir, monkeypatch) -> tuple[int, str, list[Path]]:
    upgrade_head()
    monkeypatch.setattr("config.app_settings.OCR_AGENT_ENABLED", True)
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

    job = ocr_agent_jobs.claim("windows-ocr-1")

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
    first = ocr_agent_jobs.claim("windows-ocr-1")
    second = ocr_agent_jobs.claim("windows-ocr-1")

    assert first is not None and second is not None
    assert first["id"] == second["id"] == job_id
    with pytest.raises(ValueError, match="claim"):
        ocr_agent_jobs.image_path(job_id, "windows-ocr-2", book_name, 1)


def test_agent_rejects_page_hash_mismatch(agent_job) -> None:
    job_id, book_name, paths = agent_job
    ocr_agent_jobs.claim("windows-ocr-1")
    page = _page(1, paths[0])
    page["image_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="SHA-256"):
        ocr_agent_jobs.submit_page(job_id, "windows-ocr-1", book_name, page)
