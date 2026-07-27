"""公開中OCR runの選択と採用本文解決を一元化する。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class PublishedRun:
    """書籍ごとの現在公開中run。"""

    id: int
    book_name: str


def list_current_published_runs(
    conn: sqlite3.Connection,
    *,
    book_names: list[str] | tuple[str, ...] | None = None,
) -> list[PublishedRun]:
    """各書籍の最新承認済みrunを返す。

    公開済みの条件は ``completed + approved``。複数の承認runが残る場合は
    承認日時（未設定時は終了・開始日時）、最後にIDの降順で現在のrunを決める。
    """
    params: list[object] = []
    book_filter = ""
    if book_names is not None:
        if not book_names:
            return []
        placeholders = ", ".join("?" for _ in book_names)
        book_filter = f" AND book_name IN ({placeholders})"
        params.extend(book_names)

    rows = conn.execute(
        f"""
        WITH ranked AS (
            SELECT
                id,
                book_name,
                ROW_NUMBER() OVER (
                    PARTITION BY book_name
                    ORDER BY
                        COALESCE(qa_reviewed_at, finished_at, started_at, '') DESC,
                        id DESC
                ) AS publication_rank
            FROM ocr_runs
            WHERE state = 'completed'
              AND qa_state = 'approved'
              {book_filter}
        )
        SELECT id, book_name
        FROM ranked
        WHERE publication_rank = 1
        ORDER BY book_name
        """,
        params,
    ).fetchall()
    return [PublishedRun(id=int(row[0]), book_name=str(row[1])) for row in rows]


def resolve_selected_text(
    *,
    full_text: str | None,
    primary_text: str | None,
    external_text: str | None,
    selected_engine: str | None,
    corrected_text: str | None,
) -> str:
    """selected_engineに従い、公開候補として採用された本文を返す。"""
    primary = primary_text or full_text or ""
    return {
        "primary": primary,
        "external": external_text or "",
        "codex": corrected_text or "",
    }.get(selected_engine or "primary", full_text or "")
