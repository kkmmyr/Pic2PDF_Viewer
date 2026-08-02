"""Kindle capture jobの状態とSQLite transaction。"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta

from services.kindle_catalog.connection import with_db
from utils.logger import get_logger

logger = get_logger(__name__)

ACTIVE_STATUSES = (
    "claimed",
    "locating_book",
    "downloading",
    "positioning",
    "waiting_user",
    "capturing",
    "awaiting_files",
)
UNFINISHED_STATUSES = ("queued", *ACTIVE_STATUSES)
AGENT_TRANSITIONS = {
    "claimed": {"locating_book", "waiting_user", "failed"},
    "locating_book": {"downloading", "positioning", "failed"},
    "downloading": {"positioning", "failed"},
    "positioning": {"capturing", "failed"},
    "waiting_user": {"capturing", "failed"},
    "capturing": {"capturing", "awaiting_files", "failed"},
    "awaiting_files": {"failed"},
}


def row_dict(row) -> dict:
    return dict(row)


def _job_with_identity(conn: sqlite3.Connection, job_id: str) -> dict:
    row = conn.execute(
        """
        SELECT
            cj.*,
            b.title,
            b.title_normalized,
            s.name AS series_name,
            bs.volume_number,
            bs.volume_label
        FROM capture_jobs cj
        JOIN books b ON b.asin=cj.asin
        LEFT JOIN book_series bs ON bs.asin=b.asin
        LEFT JOIN series s ON s.id=bs.series_id
        WHERE cj.id=?
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        raise ValueError("キャプチャジョブが見つかりません")
    job = row_dict(row)
    authors = conn.execute(
        """
        SELECT a.name
        FROM book_authors ba
        JOIN authors a ON a.id=ba.author_id
        WHERE ba.asin=?
        ORDER BY ba.sort_order, ba.id
        """,
        (job["asin"],),
    ).fetchall()
    job["identity"] = {
        "asin": job["asin"],
        "title": job["title"],
        "title_normalized": job["title_normalized"],
        "authors": [author["name"] for author in authors],
        "series_name": job["series_name"],
        "volume_number": job["volume_number"],
        "volume_label": job["volume_label"],
    }
    return job


def _recover_stale(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    timeout_seconds: int,
) -> list[str]:
    if timeout_seconds <= 0:
        raise ValueError("heartbeat timeout は 1 秒以上で指定してください")
    cutoff = (now - timedelta(seconds=timeout_seconds)).isoformat()
    placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
    rows = conn.execute(
        f"""
        SELECT id
        FROM capture_jobs
        WHERE status IN ({placeholders})
          AND COALESCE(heartbeat_at, claimed_at, requested_at) < ?
        ORDER BY requested_at
        """,
        (*ACTIVE_STATUSES, cutoff),
    ).fetchall()
    job_ids = [row["id"] for row in rows]
    if not job_ids:
        return []
    completed_at = now.isoformat()
    conn.execute(
        f"""
        UPDATE capture_jobs SET
            status='failed',
            completed_at=?,
            error_code='agent_heartbeat_timeout',
            error_message='キャプチャエージェントの heartbeat が期限切れです'
        WHERE status IN ({placeholders})
          AND COALESCE(heartbeat_at, claimed_at, requested_at) < ?
        """,
        (completed_at, *ACTIVE_STATUSES, cutoff),
    )
    logger.warning("Recovered %d stale Kindle capture job(s)", len(job_ids))
    return job_ids


def create(
    asin: str,
    source: str,
    direction: str,
    expected_screens: int | None,
    *,
    requested_at: datetime,
    timeout_seconds: int,
) -> dict:
    if source not in {"comic", "novel"}:
        raise ValueError("source は comic または novel です")
    if direction not in {"left", "right"}:
        raise ValueError("direction は left または right です")
    with with_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _recover_stale(
            conn,
            now=requested_at,
            timeout_seconds=timeout_seconds,
        )
        book = conn.execute("SELECT asin FROM books WHERE asin=?", (asin,)).fetchone()
        if book is None:
            raise ValueError("指定 ASIN は Kindle カタログに存在しません")
        placeholders = ",".join("?" for _ in UNFINISHED_STATUSES)
        existing = conn.execute(
            f"SELECT id,asin FROM capture_jobs WHERE status IN ({placeholders}) LIMIT 1",
            UNFINISHED_STATUSES,
        ).fetchone()
        if existing:
            raise ValueError("別の未完了キャプチャジョブがあるため作成できません")
        job_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO capture_jobs(
                id,asin,source,status,direction,expected_screens,requested_at
            ) VALUES (?,?,?,'queued',?,?,?)
            """,
            (
                job_id,
                asin,
                source,
                direction,
                expected_screens,
                requested_at.isoformat(),
            ),
        )
        row = conn.execute("SELECT * FROM capture_jobs WHERE id=?", (job_id,)).fetchone()
    return row_dict(row)


def list_jobs(limit: int = 100) -> list[dict]:
    with with_db() as conn:
        rows = conn.execute(
            """
            SELECT cj.*, b.title
            FROM capture_jobs cj JOIN books b ON b.asin=cj.asin
            ORDER BY cj.requested_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_dict(row) for row in rows]


def claim(
    agent_id: str,
    *,
    now: datetime,
    timeout_seconds: int,
) -> dict | None:
    """transaction内の条件付きUPDATEで次の1件だけをclaimする。"""
    with with_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _recover_stale(
            conn,
            now=now,
            timeout_seconds=timeout_seconds,
        )
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        active = conn.execute(
            f"""
            SELECT id FROM capture_jobs
            WHERE agent_id=? AND status IN ({placeholders})
            """,
            (agent_id, *ACTIVE_STATUSES),
        ).fetchone()
        if active:
            conn.execute(
                "UPDATE capture_jobs SET heartbeat_at=? WHERE id=?",
                (now.isoformat(), active["id"]),
            )
            return _job_with_identity(conn, active["id"])
        queued = conn.execute(
            "SELECT id FROM capture_jobs WHERE status='queued' ORDER BY requested_at LIMIT 1"
        ).fetchone()
        if queued is None:
            return None
        now_value = now.isoformat()
        updated = conn.execute(
            """
            UPDATE capture_jobs
            SET status='claimed',agent_id=?,claimed_at=?,heartbeat_at=?
            WHERE id=? AND status='queued'
            """,
            (agent_id, now_value, now_value, queued["id"]),
        ).rowcount
        if updated != 1:
            return None
        return _job_with_identity(conn, queued["id"])


def heartbeat(
    job_id: str,
    agent_id: str,
    *,
    now: datetime,
) -> dict:
    """agent所有のactive jobのheartbeatを更新する。"""
    with with_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status,agent_id FROM capture_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError("キャプチャジョブが見つかりません")
        if row["agent_id"] != agent_id:
            raise ValueError("このエージェントが claim したジョブではありません")
        if row["status"] not in ACTIVE_STATUSES:
            raise ValueError("heartbeat を更新できるジョブ状態ではありません")
        heartbeat_at = now.isoformat()
        updated = conn.execute(
            """
            UPDATE capture_jobs SET heartbeat_at=?
            WHERE id=? AND agent_id=? AND status=?
            """,
            (heartbeat_at, job_id, agent_id, row["status"]),
        ).rowcount
        if updated != 1:
            raise ValueError("heartbeat の更新に失敗しました")
    return {
        "job_id": job_id,
        "status": row["status"],
        "heartbeat_at": heartbeat_at,
    }


def update_state(
    job_id: str,
    agent_id: str,
    state: str,
    *,
    now: datetime,
    captured_screens: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict:
    if captured_screens is not None and captured_screens < 0:
        raise ValueError("captured_screens は 0 以上で指定してください")
    if state == "failed" and not error_code:
        raise ValueError("failed への遷移には error_code が必要です")
    with with_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM capture_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("キャプチャジョブが見つかりません")
        if row["agent_id"] != agent_id:
            raise ValueError("このエージェントが claim したジョブではありません")
        if state not in AGENT_TRANSITIONS.get(row["status"], set()):
            raise ValueError(f"許可されていない状態遷移です: {row['status']} -> {state}")
        now_value = now.isoformat()
        started_at = now_value if state == "capturing" and row["started_at"] is None else row["started_at"]
        completed_at = now_value if state == "failed" else row["completed_at"]
        screen_count = row["captured_screens"] if captured_screens is None else captured_screens
        updated_count = conn.execute(
            """
            UPDATE capture_jobs SET
                status=?,started_at=?,completed_at=?,captured_screens=?,
                error_code=?,error_message=?,heartbeat_at=?
            WHERE id=? AND agent_id=? AND status=?
            """,
            (
                state,
                started_at,
                completed_at,
                screen_count,
                error_code,
                error_message,
                now_value,
                job_id,
                agent_id,
                row["status"],
            ),
        ).rowcount
        if updated_count != 1:
            raise ValueError("キャプチャジョブの状態更新に失敗しました")
        updated = conn.execute("SELECT * FROM capture_jobs WHERE id=?", (job_id,)).fetchone()
    return row_dict(updated)
