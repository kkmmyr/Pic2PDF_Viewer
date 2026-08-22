"""Capture job完了時のcatalog DB境界。"""

import json
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
    quality_audit: dict,
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
        job = conn.execute(
            "SELECT asin,source FROM capture_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if job is None:
            raise ValueError("キャプチャジョブが見つかりません")
        conn.execute(
            """
            UPDATE capture_quality_audits SET
                superseded_at=?,superseded_by_job_id=?
            WHERE source=? AND book_id=? AND superseded_at IS NULL
            """,
            (completed_value, job_id, job["source"], book_id),
        )
        audit_id = conn.execute(
            """
            INSERT INTO capture_quality_audits(
                job_id,asin,source,book_id,qa_policy_version,
                warning_policy_version,quality_sha256,created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                job_id,
                job["asin"],
                job["source"],
                book_id,
                quality_audit["qa_policy_version"],
                quality_audit["warning_policy_version"],
                quality_audit["quality_sha256"],
                completed_value,
            ),
        ).lastrowid
        if audit_id is None:
            raise ValueError("画像QA監査世代の保存に失敗しました")
        for warning in quality_audit["warnings"]:
            conn.execute(
                """
                INSERT INTO capture_quality_warnings(
                    audit_id,code,finding_count,files_json,findings_json,
                    is_read,read_at
                ) VALUES (?,?,?,?,?,0,NULL)
                """,
                (
                    audit_id,
                    warning["code"],
                    warning["finding_count"],
                    json.dumps(warning["files"], ensure_ascii=False),
                    json.dumps(warning["findings"], ensure_ascii=False),
                ),
            )
