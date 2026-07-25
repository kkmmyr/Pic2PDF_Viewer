"""Kindle 購入カタログの一覧・統計クエリ。"""

from __future__ import annotations

import sqlite3

from services.kindle_catalog.connection import with_db
from services.meta_db import create_tables, db_connection


def _capture_counts(asins: list[str]) -> dict[str, int]:
    if not asins:
        return {}
    placeholders = ",".join("?" for _ in asins)
    with db_connection() as conn:
        create_tables(conn)
        rows = conn.execute(
            f"""
            SELECT asin, COUNT(*) AS count
            FROM books_meta
            WHERE source IN ('comic', 'novel') AND asin IN ({placeholders})
            GROUP BY asin
            """,
            asins,
        ).fetchall()
    return {row["asin"]: row["count"] for row in rows}


def _capture_state(link_count: int, pending: bool) -> str:
    if pending:
        return "capture_pending"
    if link_count == 1:
        return "captured"
    if link_count > 1:
        return "multiple_links"
    return "not_captured"


def _ownership(row: sqlite3.Row) -> str:
    if row["has_return"]:
        return "returned"
    if row["has_purchase"]:
        return "purchased"
    if row["has_active_borrowing"]:
        return "borrowed_active"
    if row["has_borrowing"]:
        return "borrowed_ended"
    return "unknown"


def list_books(
    *,
    q: str | None,
    book_type: str | None,
    ownership: str | None,
    capture_state: str | None,
    page: int,
    page_size: int,
) -> dict:
    where: list[str] = []
    params: list[object] = []
    if q:
        where.append(
            "(b.title LIKE ? OR b.asin LIKE ? OR EXISTS ("
            "SELECT 1 FROM book_authors ba JOIN authors a ON a.id=ba.author_id "
            "WHERE ba.asin=b.asin AND a.name LIKE ?))"
        )
        pattern = f"%{q}%"
        params.extend((pattern, pattern, pattern))
    if book_type:
        where.append("b.book_type=?")
        params.append(book_type)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    base_sql = f"""
        SELECT b.*,
            EXISTS(SELECT 1 FROM purchases p WHERE p.asin=b.asin) AS has_purchase,
            EXISTS(SELECT 1 FROM borrowings br WHERE br.asin=b.asin) AS has_borrowing,
            EXISTS(
                SELECT 1 FROM borrowings br
                WHERE br.asin=b.asin
                  AND (br.end_date IS NULL OR br.loan_status IN ('ACTIVE', 'BORROWED', 'LOANED'))
            ) AS has_active_borrowing,
            EXISTS(SELECT 1 FROM returns r WHERE r.asin=b.asin) AS has_return,
            EXISTS(
                SELECT 1 FROM capture_jobs cj
                WHERE cj.asin=b.asin
                  AND cj.status IN ('queued','claimed','waiting_user','capturing','awaiting_files')
            ) AS capture_pending,
            (SELECT GROUP_CONCAT(name, ' / ') FROM (
                SELECT a.name AS name
                FROM book_authors ba JOIN authors a ON a.id=ba.author_id
                WHERE ba.asin=b.asin ORDER BY ba.sort_order
            )) AS authors,
            (SELECT GROUP_CONCAT(genre, ' / ') FROM (
                SELECT genre FROM book_genres bg WHERE bg.asin=b.asin ORDER BY genre
            )) AS genres,
            s.id AS series_id, s.name AS series_name,
            bs.volume_number, bs.volume_label
        FROM books b
        LEFT JOIN book_series bs ON bs.asin=b.asin
        LEFT JOIN series s ON s.id=bs.series_id
        {where_sql}
        ORDER BY COALESCE(b.kindle_acquisition_date, b.created_at) DESC, b.title
    """
    with with_db() as conn:
        rows = conn.execute(base_sql, params).fetchall()

    captures = _capture_counts([row["asin"] for row in rows])
    items = []
    for row in rows:
        ownership_value = _ownership(row)
        capture_value = _capture_state(captures.get(row["asin"], 0), bool(row["capture_pending"]))
        if ownership and ownership_value != ownership:
            continue
        if capture_state and capture_value != capture_state:
            continue
        items.append(
            {
                "asin": row["asin"],
                "title": row["title"],
                "authors": row["authors"].split(" / ") if row["authors"] else [],
                "genres": row["genres"].split(" / ") if row["genres"] else [],
                "publisher": row["publisher"],
                "book_type": row["book_type"],
                "kindle_acquisition_date": row["kindle_acquisition_date"],
                "is_completed": bool(row["is_completed"]) if row["is_completed"] is not None else None,
                "ownership": ownership_value,
                "capture_state": capture_value,
                "series_id": row["series_id"],
                "series_name": row["series_name"],
                "volume_number": row["volume_number"],
                "volume_label": row["volume_label"],
            }
        )
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start : start + page_size], "total": total, "page": page, "page_size": page_size}


def stats() -> dict:
    with with_db() as conn:
        books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        purchases = conn.execute("SELECT COUNT(*) FROM purchases").fetchone()[0]
        borrowings = conn.execute("SELECT COUNT(*) FROM borrowings").fetchone()[0]
        returns = conn.execute("SELECT COUNT(*) FROM returns").fetchone()[0]
        series = conn.execute("SELECT COUNT(*) FROM series").fetchone()[0]
        last_run = conn.execute(
            "SELECT id, source_kind, status, started_at, finished_at, files_processed, "
            "records_processed, records_skipped, error_message "
            "FROM import_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    with db_connection() as meta_conn:
        create_tables(meta_conn)
        captured = meta_conn.execute(
            "SELECT COUNT(DISTINCT asin) FROM books_meta "
            "WHERE source IN ('comic','novel') AND asin IS NOT NULL AND TRIM(asin) <> ''"
        ).fetchone()[0]
    return {
        "books": books,
        "purchases": purchases,
        "borrowings": borrowings,
        "returns": returns,
        "series": series,
        "captured": captured,
        "last_import": dict(last_run) if last_run else None,
    }


def list_import_runs(limit: int = 50) -> list[dict]:
    with with_db() as conn:
        rows = conn.execute(
            "SELECT * FROM import_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
