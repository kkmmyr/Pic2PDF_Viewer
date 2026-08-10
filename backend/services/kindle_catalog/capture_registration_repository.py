"""Capture job完了時のcatalog DB境界。"""

from datetime import datetime

from services.kindle_catalog.capture_job_repository import row_dict
from services.kindle_catalog.connection import with_db


def load_awaiting_job(job_id: str, agent_id: str) -> dict:
    with with_db() as conn:
        row = conn.execute(
            """
            SELECT cj.*, b.title
            FROM capture_jobs cj JOIN books b ON b.asin=cj.asin
            WHERE cj.id=?
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        raise ValueError("キャプチャジョブが見つかりません")
    job = row_dict(row)
    if job["agent_id"] != agent_id or job["status"] != "awaiting_files":
        raise ValueError("完了報告できるジョブ状態ではありません")
    return job


def mark_succeeded(
    job_id: str,
    agent_id: str,
    *,
    completed_at: datetime,
    book_id: str,
    captured_screens: int,
) -> None:
    completed_value = completed_at.isoformat()
    with with_db() as conn:
        updated = conn.execute(
            """
            UPDATE capture_jobs SET
                status='succeeded',completed_at=?,heartbeat_at=?,
                book_id=?,captured_screens=?
            WHERE id=? AND status='awaiting_files' AND agent_id=?
            """,
            (
                completed_value,
                completed_value,
                book_id,
                captured_screens,
                job_id,
                agent_id,
            ),
        ).rowcount
        if updated != 1:
            raise ValueError("キャプチャジョブの完了更新に失敗しました")
