"""Kindle Info CSVのsource別upsert。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from services.kindle_catalog.book_classifier import classify_book_type
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.enrichment_files import (
    KINDLE_INFO_FILES,
    clean,
    find_exact,
    is_imported,
    read_csv,
    record_file,
    sha256_file,
    timestamp,
)
from services.kindle_catalog.import_run_lifecycle import (
    fail_import_run,
    finish_import_run,
    start_import_run,
)
from utils.dt import jst_now


def _book_exists(conn: Any, asin: str) -> bool:
    return conn.execute("SELECT 1 FROM books WHERE asin=?", (asin,)).fetchone() is not None


def _import_acquisition_dates(
    conn: Any,
    rows: list[dict[str, str]],
) -> tuple[int, int]:
    changed = skipped = 0
    seen: set[str] = set()
    for row in rows:
        asin = (clean(row.get("ASIN")) or "").upper()
        acquired = timestamp(row.get("Relationship Creation Date"))
        if not asin or asin in seen or not acquired:
            continue
        seen.add(asin)
        if not _book_exists(conn, asin):
            skipped += 1
            continue
        before = conn.total_changes
        conn.execute(
            """
            UPDATE books SET kindle_acquisition_date=?
            WHERE asin=? AND kindle_acquisition_date IS NULL
            """,
            (acquired, asin),
        )
        changed += int(conn.total_changes > before)
    return changed, skipped


def _import_genres(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        asin = (clean(row.get("ASIN")) or "").upper()
        genre = clean(row.get("Genre"))
        if asin and genre and genre not in grouped[asin]:
            grouped[asin].append(genre)
    changed = skipped = 0
    for asin, genres in grouped.items():
        book = conn.execute(
            "SELECT title,book_type FROM books WHERE asin=?",
            (asin,),
        ).fetchone()
        if book is None:
            skipped += 1
            continue
        conn.execute("DELETE FROM book_genres WHERE asin=?", (asin,))
        conn.executemany(
            "INSERT INTO book_genres(asin,genre) VALUES (?,?)",
            ((asin, genre) for genre in genres),
        )
        book_type = classify_book_type(genres, book["title"])
        if book_type:
            conn.execute("UPDATE books SET book_type=? WHERE asin=?", (book_type, asin))
        changed += 1
    return changed, skipped


def _import_authors(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        asin = (clean(row.get("ASIN")) or "").upper()
        author = clean(row.get("Author Name"))
        if asin and author and author not in grouped[asin]:
            grouped[asin].append(author)
    changed = skipped = 0
    for asin, authors in grouped.items():
        if not _book_exists(conn, asin):
            skipped += 1
            continue
        if conn.execute(
            "SELECT 1 FROM book_authors WHERE asin=? LIMIT 1",
            (asin,),
        ).fetchone():
            continue
        for order, author in enumerate(authors):
            key = " ".join(author.casefold().split())
            conn.execute(
                """
                INSERT INTO authors(name,name_key) VALUES (?,?)
                ON CONFLICT(name_key) DO UPDATE SET name=excluded.name
                """,
                (author, key),
            )
            author_id = conn.execute(
                "SELECT id FROM authors WHERE name_key=?",
                (key,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO book_authors(asin,author_id,sort_order) VALUES (?,?,?)",
                (asin, author_id, order),
            )
        changed += 1
    return changed, skipped


def _import_volumes(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    changed = skipped = 0
    for row in rows:
        if clean(row.get("record-type")) != "Item":
            continue
        asin = (clean(row.get("item-ASIN")) or "").upper()
        raw_volume = clean(row.get("item-position-in-series"))
        if not asin or not raw_volume:
            continue
        try:
            volume = float(raw_volume)
        except ValueError:
            continue
        if not _book_exists(conn, asin):
            skipped += 1
            continue
        before = conn.total_changes
        conn.execute(
            """
            UPDATE book_series
            SET volume_number=?, detection_method='kindle_info', updated_at=?
            WHERE asin=? AND volume_number IS NULL AND is_manually_edited=0
            """,
            (volume, jst_now().isoformat(), asin),
        )
        changed += int(conn.total_changes > before)
    return changed, skipped


def _update_existing(
    conn: Any,
    values: dict[str, int],
    column: str,
) -> tuple[int, int]:
    if column not in {"total_reading_ms", "is_completed"}:
        raise ValueError("更新対象列が不正です")
    changed = skipped = 0
    for asin, value in values.items():
        if not asin or not _book_exists(conn, asin):
            skipped += 1
            continue
        conn.execute(f"UPDATE books SET {column}=? WHERE asin=?", (value, asin))
        changed += 1
    return changed, skipped


def _import_reading(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        asin = (clean(row.get("ASIN")) or "").upper()
        try:
            totals[asin] += int(clean(row.get("total_reading_milliseconds")) or "0")
        except ValueError:
            continue
    return _update_existing(conn, totals, "total_reading_ms")


def _import_last_read(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    latest: dict[str, str] = {}
    for row in rows:
        if clean(row.get("Annotation Type")) != "kindle.last_read":
            continue
        asin = (clean(row.get("ASIN")) or "").upper()
        modified = timestamp(row.get("Customer modified date on device"))
        if asin and modified and modified > latest.get(asin, ""):
            latest[asin] = modified
    changed = skipped = 0
    for asin, modified in latest.items():
        if not _book_exists(conn, asin):
            skipped += 1
            continue
        conn.execute(
            """
            UPDATE books SET last_read_at=?
            WHERE asin=? AND (last_read_at IS NULL OR last_read_at < ?)
            """,
            (modified, asin, modified),
        )
        changed += 1
    return changed, skipped


def _import_completed(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    asins = {asin for row in rows if (asin := (clean(row.get("file_auto_marked_as_read")) or "").upper())}
    return _update_existing(conn, dict.fromkeys(asins, 1), "is_completed")


_HANDLERS = {
    "acquisition_dates": _import_acquisition_dates,
    "genres": _import_genres,
    "authors": _import_authors,
    "volumes": _import_volumes,
    "reading": _import_reading,
    "last_read": _import_last_read,
    "completed": _import_completed,
}


def run_kindle_info_import() -> dict[str, Any]:
    run_id = start_import_run("kindle_info")
    files_processed = files_skipped = records = missing_asins = 0
    results: list[dict[str, Any]] = []
    try:
        for filename, kind in KINDLE_INFO_FILES.items():
            for path in find_exact(filename):
                digest = sha256_file(path)
                with with_db() as conn:
                    if is_imported(conn, f"kindle_info:{kind}", path, digest):
                        files_skipped += 1
                        results.append(
                            {
                                "filename": path.name,
                                "kind": kind,
                                "status": "skipped",
                                "records": 0,
                            }
                        )
                        continue
                    rows = read_csv(path)
                    count, skipped = _HANDLERS[kind](conn, rows)
                    record_file(conn, f"kindle_info:{kind}", path, digest, count)
                    files_processed += 1
                    records += count
                    missing_asins += skipped
                    results.append(
                        {
                            "filename": path.name,
                            "kind": kind,
                            "status": "success",
                            "records": count,
                        }
                    )
    except Exception as exc:
        fail_import_run(run_id, exc)
        raise
    finish_import_run(
        run_id,
        status="succeeded",
        files=files_processed,
        records=records,
        skipped=files_skipped + missing_asins,
    )
    return {
        "run_id": run_id,
        "status": "succeeded",
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "records_processed": records,
        "records_skipped": missing_asins,
        "files": results,
    }
