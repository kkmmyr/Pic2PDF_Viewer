"""登録済みKindle画像の品質warning確認状態。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from services.kindle_catalog.connection import with_db
from utils.dt import jst_now

WarningStatus = Literal["unread", "read", "all"]


def _decode(row) -> dict:
    item = dict(row)
    item["is_read"] = bool(item["is_read"])
    item["files"] = json.loads(item.pop("files_json"))
    item["findings"] = json.loads(item.pop("findings_json"))
    item["pages"] = sorted({int(name.rsplit(".", 1)[0]) for name in item["files"] if name.rsplit(".", 1)[0].isdigit()})
    return item


def _select_sql(where: str = "") -> str:
    return f"""
        SELECT
            w.id,w.audit_id,a.job_id,a.asin,b.title,a.source,a.book_id,
            a.warning_policy_version,a.created_at,w.code,w.finding_count,
            w.files_json,w.findings_json,w.is_read,w.read_at
        FROM capture_quality_warnings w
        JOIN capture_quality_audits a ON a.id=w.audit_id
        JOIN books b ON b.asin=a.asin
        WHERE a.superseded_at IS NULL {where}
    """


def list_warnings(status: WarningStatus = "unread") -> dict:
    filters = {
        "unread": "AND w.is_read=0",
        "read": "AND w.is_read=1",
        "all": "",
    }
    if status not in filters:
        raise ValueError("statusはunread、read、allのいずれかです")
    with with_db() as conn:
        counts = conn.execute(
            """
            SELECT
                SUM(CASE WHEN w.is_read=0 THEN 1 ELSE 0 END) AS unread_count,
                SUM(CASE WHEN w.is_read=1 THEN 1 ELSE 0 END) AS read_count
            FROM capture_quality_warnings w
            JOIN capture_quality_audits a ON a.id=w.audit_id
            WHERE a.superseded_at IS NULL
            """
        ).fetchone()
        rows = conn.execute(_select_sql(filters[status]) + " ORDER BY a.created_at DESC,w.id DESC").fetchall()
    items = [_decode(row) for row in rows]
    return {
        "items": items,
        "total": len(items),
        "unread_count": int(counts["unread_count"] or 0),
        "read_count": int(counts["read_count"] or 0),
    }


def set_read(
    warning_id: int,
    is_read: bool,
    *,
    now: datetime | None = None,
) -> dict:
    read_at = (now or jst_now()).isoformat() if is_read else None
    with with_db() as conn:
        updated = conn.execute(
            """
            UPDATE capture_quality_warnings
            SET is_read=?,read_at=?
            WHERE id=? AND EXISTS (
                SELECT 1 FROM capture_quality_audits a
                WHERE a.id=capture_quality_warnings.audit_id
                  AND a.superseded_at IS NULL
            )
            """,
            (int(is_read), read_at, warning_id),
        ).rowcount
        if updated != 1:
            raise ValueError("有効な品質warningが見つかりません")
        row = conn.execute(_select_sql("AND w.id=?"), (warning_id,)).fetchone()
    if row is None:
        raise ValueError("有効な品質warningが見つかりません")
    return _decode(row)
