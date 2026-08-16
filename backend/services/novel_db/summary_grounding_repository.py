"""要約根拠検査の監査ログrepository。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from .summary_grounding_parser import SummaryContentType


def save_grounding_report(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    summary: str,
    writer_model: str,
    verifier_model: str,
    content_type: SummaryContentType,
    passed: bool,
    payload: dict[str, Any],
) -> None:
    """検査結果を監査テーブルへ保存し独立commitする。"""
    conn.execute(
        """
        INSERT INTO summary_grounding_reports
            (book_id, content_type, candidate_sha256, writer_model, verifier_model, passed,
             report_json, checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', '+9 hours'))
        """,
        (
            book_id,
            content_type,
            hashlib.sha256(summary.encode("utf-8")).hexdigest(),
            writer_model,
            verifier_model,
            int(passed),
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.commit()
