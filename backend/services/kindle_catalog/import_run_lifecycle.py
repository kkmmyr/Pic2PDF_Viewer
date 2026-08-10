"""Kindle catalog取込runの共通状態遷移。"""

from services.kindle_catalog.connection import with_db
from utils.dt import jst_now


def start_import_run(source_kind: str) -> int:
    with with_db() as conn:
        return conn.execute(
            """
            INSERT INTO import_runs(
                source_kind,status,started_at,files_processed,
                records_processed,records_skipped
            ) VALUES (?,'running',?,0,0,0)
            """,
            (source_kind, jst_now().isoformat()),
        ).lastrowid


def finish_import_run(
    run_id: int,
    *,
    status: str,
    files: int = 0,
    records: int = 0,
    skipped: int = 0,
    error: str | None = None,
) -> None:
    with with_db() as conn:
        conn.execute(
            """
            UPDATE import_runs SET status=?,finished_at=?,files_processed=?,
                records_processed=?,records_skipped=?,error_message=?
            WHERE id=?
            """,
            (status, jst_now().isoformat(), files, records, skipped, error, run_id),
        )


def fail_import_run(run_id: int, error: Exception) -> None:
    finish_import_run(run_id, status="failed", error=str(error))
