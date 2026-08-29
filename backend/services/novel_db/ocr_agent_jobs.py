"""Server-owned job coordination for the Windows OCR inference agent."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import config

from .connection import with_db
from .extractor import OcrPageResult
from .ocr_qa_staging import stage_run_for_qa
from .ocr_run_store import collect_input_pages, mark_run_failed, prepare_run, save_page_result


def _require_owned_job(job_id: int, agent_id: str) -> None:
    with with_db() as conn:
        row = conn.execute(
            "SELECT state, agent_id FROM rebuild_jobs WHERE id=? AND mode='ocr'",
            (job_id,),
        ).fetchone()
    if row is None:
        raise LookupError(f"OCR agent job not found: {job_id}")
    if row[0] != "running" or row[1] != agent_id:
        raise ValueError("このエージェントがclaimしたOCRジョブではありません")


def _targets(job_type: str, target_id: str | None) -> list[str]:
    if job_type == "book":
        if not target_id:
            raise ValueError("book OCR job has no target")
        return [target_id]
    if job_type != "all":
        raise ValueError(f"unsupported OCR agent job type: {job_type}")
    images_dir = Path(config.KINDLE_NOVEL_IMAGES_DIR)
    if not images_dir.exists():
        return []
    all_dirs = {path.name for path in images_dir.iterdir() if path.is_dir()}
    with with_db() as conn:
        rows = conn.execute("SELECT name FROM books WHERE ocr_done_at IS NOT NULL").fetchall()
    return sorted(all_dirs - {str(row[0]) for row in rows})


def _manifest(job_id: int, agent_id: str) -> dict:
    _require_owned_job(job_id, agent_id)
    with with_db() as conn:
        job = conn.execute(
            "SELECT job_type, target_id, progress_total, progress_done FROM rebuild_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        mappings = conn.execute(
            "SELECT book_name, run_id FROM ocr_agent_job_runs WHERE job_id=? ORDER BY book_name",
            (job_id,),
        ).fetchall()
    books: list[dict] = []
    for mapping in mappings:
        book_name = str(mapping[0])
        run_id = int(mapping[1])
        input_pages = collect_input_pages(book_name)
        with with_db() as conn:
            passed = conn.execute(
                "SELECT page_no, image_sha256 FROM ocr_page_results WHERE run_id=? AND state='passed'",
                (run_id,),
            ).fetchall()
        passed_hashes = {int(row[0]): str(row[1]) for row in passed}
        tasks = [
            {
                "book_name": book_name,
                "page_no": page.page_no,
                "image_sha256": page.image_sha256,
                "image_url": (f"/api/ocr/agents/jobs/{job_id}/pages/{quote(book_name, safe='')}/{page.page_no}/image"),
            }
            for page in input_pages
            if passed_hashes.get(page.page_no) != page.image_sha256
        ]
        books.append(
            {
                "book_name": book_name,
                "run_id": run_id,
                "source_page_count": len(input_pages),
                "tasks": tasks,
            }
        )
    return {
        "id": job_id,
        "job_type": str(job[0]),
        "target_id": job[1],
        "agent_id": agent_id,
        "progress_total": int(job[2] or len(books)),
        "progress_done": int(job[3] or 0),
        "books": books,
    }


def _recover_stale_jobs() -> None:
    timeout = config.app_settings.OCR_AGENT_HEARTBEAT_TIMEOUT_SEC
    modifier = f"-{timeout} seconds"
    with with_db() as conn:
        stale = conn.execute(
            "SELECT id FROM rebuild_jobs WHERE mode='ocr' AND state='running' "
            "AND agent_id IS NOT NULL AND COALESCE(heartbeat_at, started_at) "
            "< datetime('now', '+9 hours', ?)",
            (modifier,),
        ).fetchall()
        with conn:
            for row in stale:
                job_id = int(row[0])
                conn.execute(
                    "UPDATE rebuild_jobs SET state='failed', finished_at=datetime('now', '+9 hours'), "
                    "error_message='OCR agent heartbeat timeout' WHERE id=?",
                    (job_id,),
                )
                run_rows = conn.execute(
                    "SELECT run_id FROM ocr_agent_job_runs WHERE job_id=?",
                    (job_id,),
                ).fetchall()
                for run_row in run_rows:
                    conn.execute(
                        "UPDATE ocr_runs SET state='failed', finished_at=datetime('now', '+9 hours'), "
                        "error_message='OCR agent heartbeat timeout' WHERE id=?",
                        (int(run_row[0]),),
                    )


def claim(agent_id: str, model_revision: str | None = None) -> dict | None:
    _recover_stale_jobs()
    with with_db() as conn:
        existing = conn.execute(
            "SELECT id FROM rebuild_jobs WHERE mode='ocr' AND state='running' AND agent_id=? "
            "ORDER BY started_at LIMIT 1",
            (agent_id,),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE rebuild_jobs SET heartbeat_at=datetime('now', '+9 hours') WHERE id=?",
                (int(existing[0]),),
            )
            conn.commit()
            return _manifest(int(existing[0]), agent_id)

        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, job_type, target_id FROM rebuild_jobs "
            "WHERE mode='ocr' AND state='queued' ORDER BY enqueued_at, id LIMIT 1"
        ).fetchone()
        if row is None:
            conn.rollback()
            return None
        job_id = int(row[0])
        cursor = conn.execute(
            "UPDATE rebuild_jobs SET state='running', agent_id=?, "
            "started_at=datetime('now', '+9 hours'), heartbeat_at=datetime('now', '+9 hours'), "
            "current_step='ocr_agent_claimed' WHERE id=? AND state='queued'",
            (agent_id, job_id),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None
        conn.commit()

    try:
        engine = config.app_settings.OCR_ENGINE.casefold()
        model = model_revision or (config.app_settings.SURYA_MODEL_REVISION if engine == "surya2" else engine)
        targets = _targets(str(row[1]), row[2])
        prepared: list[tuple[str, int]] = []
        for book_name in targets:
            input_pages = collect_input_pages(book_name)
            run_id, _ = prepare_run(book_name, engine, model, input_pages)
            prepared.append((book_name, run_id))
        with with_db() as conn:
            with conn:
                conn.execute(
                    "UPDATE rebuild_jobs SET progress_total=?, progress_done=0 WHERE id=?",
                    (len(targets), job_id),
                )
                for book_name, run_id in prepared:
                    conn.execute(
                        "INSERT OR REPLACE INTO ocr_agent_job_runs (job_id, run_id, book_name) VALUES (?, ?, ?)",
                        (job_id, run_id, book_name),
                    )
    except Exception as exc:
        fail(job_id, agent_id, str(exc))
        raise
    return _manifest(job_id, agent_id)


def heartbeat(job_id: int, agent_id: str) -> dict:
    _require_owned_job(job_id, agent_id)
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET heartbeat_at=datetime('now', '+9 hours') "
            "WHERE id=? AND agent_id=? AND state='running'",
            (job_id, agent_id),
        )
        conn.commit()
    return {"job_id": job_id, "status": "running"}


def image_path(job_id: int, agent_id: str, book_name: str, page_no: int) -> Path:
    _require_owned_job(job_id, agent_id)
    with with_db() as conn:
        mapping = conn.execute(
            "SELECT 1 FROM ocr_agent_job_runs WHERE job_id=? AND book_name=?",
            (job_id, book_name),
        ).fetchone()
    if mapping is None:
        raise LookupError("OCR agent manifestに含まれない書籍です")
    pages = collect_input_pages(book_name)
    if page_no < 1 or page_no > len(pages):
        raise LookupError("OCR agent manifestに含まれない画面です")
    return pages[page_no - 1].image_path


def submit_page(
    job_id: int,
    agent_id: str,
    book_name: str,
    page: OcrPageResult,
) -> dict:
    _require_owned_job(job_id, agent_id)
    with with_db() as conn:
        mapping = conn.execute(
            "SELECT run_id FROM ocr_agent_job_runs WHERE job_id=? AND book_name=?",
            (job_id, book_name),
        ).fetchone()
    if mapping is None:
        raise LookupError("OCR agent manifestに含まれない書籍です")
    input_pages = collect_input_pages(book_name)
    page_no = int(page["page_no"])
    if page_no < 1 or page_no > len(input_pages):
        raise ValueError("OCR agent manifestに含まれない画面です")
    expected = input_pages[page_no - 1]
    if page["image_sha256"] != expected.image_sha256:
        raise ValueError("OCR page image SHA-256 mismatch")
    save_page_result(int(mapping[0]), page)
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET heartbeat_at=datetime('now', '+9 hours'), current_detail=? WHERE id=?",
            (f"{book_name} | page {page_no}", job_id),
        )
        conn.commit()
    return {"job_id": job_id, "book_name": book_name, "page_no": page_no, "status": page["state"]}


def complete(job_id: int, agent_id: str) -> dict:
    _require_owned_job(job_id, agent_id)
    with with_db() as conn:
        mappings = conn.execute(
            "SELECT book_name, run_id FROM ocr_agent_job_runs WHERE job_id=? ORDER BY book_name",
            (job_id,),
        ).fetchall()
    for done, mapping in enumerate(mappings, start=1):
        input_pages = collect_input_pages(str(mapping[0]))
        stage_run_for_qa(int(mapping[1]), input_pages)
        with with_db() as conn:
            conn.execute(
                "UPDATE rebuild_jobs SET progress_done=?, heartbeat_at=datetime('now', '+9 hours') WHERE id=?",
                (done, job_id),
            )
            conn.commit()
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET state='completed', finished_at=datetime('now', '+9 hours'), "
            "current_step='awaiting_qa', error_message=NULL WHERE id=?",
            (job_id,),
        )
        conn.commit()
    return {"job_id": job_id, "status": "completed", "books": len(mappings)}


def fail(job_id: int, agent_id: str, error: str) -> dict:
    _require_owned_job(job_id, agent_id)
    with with_db() as conn:
        run_rows = conn.execute(
            "SELECT run_id FROM ocr_agent_job_runs WHERE job_id=?",
            (job_id,),
        ).fetchall()
    for row in run_rows:
        mark_run_failed(int(row[0]), error)
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET state='failed', finished_at=datetime('now', '+9 hours'), "
            "error_message=? WHERE id=?",
            (error, job_id),
        )
        conn.commit()
    return {"job_id": job_id, "status": "failed"}
