"""Kindle Info CSV とシリーズ自動購入 JSON の差分取り込み。"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import config
from services._title_normalizer import normalize_title
from services.kindle_catalog.book_classifier import classify_book_type
from services.kindle_catalog.connection import with_db
from utils.dt import jst_now

_KINDLE_INFO_FILES = {
    "Kindle.UnifiedLibraryIndex.CustomerRelationshipIndex_FE.csv": "acquisition_dates",
    "Kindle.UnifiedLibraryIndex.CustomerGenres_FE.csv": "genres",
    "Kindle.UnifiedLibraryIndex.CustomerAuthorNameRelationship_FE.csv": "authors",
    "Kindle.SagaSeriesInfra.CollectionRightsDatastore.csv": "volumes",
    "Kindle.reading-insights-sessions_with_adjustments.csv": "reading",
    "whispersync.csv": "last_read",
    "Kindle.Devices.autoMarkAsRead.csv": "completed",
}
_AUTOBUY_FILENAME = "kindle-series-autobuy.json"
_NA_VALUES = {"", "not available", "not applicable"}


def _root() -> Path:
    raw = config.AMAZON_DATA_DIR
    if not raw:
        raise ValueError("AMAZON_DATA_DIR が設定されていません")
    root = Path(raw).resolve()
    if not root.is_dir():
        raise ValueError("設定された AMAZON_DATA_DIR が見つかりません")
    return root


def _find_exact(filename: str) -> list[Path]:
    root = _root()
    return sorted(
        (path.resolve() for path in root.rglob(filename) if path.is_file() and root in path.resolve().parents),
        key=lambda path: str(path).casefold(),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "cp932", "utf-8"):
        try:
            with path.open("r", encoding=encoding, newline="") as source:
                return list(csv.DictReader(source))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path.name} の文字コードを判定できません")


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return None if text.casefold() in _NA_VALUES else text


def _timestamp(value: object) -> str | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def _book_exists(conn: Any, asin: str) -> bool:
    return conn.execute("SELECT 1 FROM books WHERE asin=?", (asin,)).fetchone() is not None


def _record_file(conn: Any, kind: str, path: Path, digest: str, count: int) -> None:
    conn.execute(
        """
        INSERT INTO imported_files(source_kind,filename,sha256,imported_at,record_count,status)
        VALUES (?,?,?,?,?,'success')
        """,
        (kind, path.name, digest, jst_now().isoformat(), count),
    )


def _is_imported(conn: Any, kind: str, path: Path, digest: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM imported_files WHERE source_kind=? AND filename=? AND sha256=?",
            (kind, path.name, digest),
        ).fetchone()
        is not None
    )


def _import_acquisition_dates(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    changed = skipped = 0
    seen: set[str] = set()
    for row in rows:
        asin = (_clean(row.get("ASIN")) or "").upper()
        acquired = _timestamp(row.get("Relationship Creation Date"))
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
        asin = (_clean(row.get("ASIN")) or "").upper()
        genre = _clean(row.get("Genre"))
        if asin and genre and genre not in grouped[asin]:
            grouped[asin].append(genre)
    changed = skipped = 0
    for asin, genres in grouped.items():
        book = conn.execute("SELECT title,book_type FROM books WHERE asin=?", (asin,)).fetchone()
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
        asin = (_clean(row.get("ASIN")) or "").upper()
        author = _clean(row.get("Author Name"))
        if asin and author and author not in grouped[asin]:
            grouped[asin].append(author)
    changed = skipped = 0
    for asin, authors in grouped.items():
        if not _book_exists(conn, asin):
            skipped += 1
            continue
        if conn.execute("SELECT 1 FROM book_authors WHERE asin=? LIMIT 1", (asin,)).fetchone():
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
            author_id = conn.execute("SELECT id FROM authors WHERE name_key=?", (key,)).fetchone()[0]
            conn.execute(
                "INSERT INTO book_authors(asin,author_id,sort_order) VALUES (?,?,?)",
                (asin, author_id, order),
            )
        changed += 1
    return changed, skipped


def _import_volumes(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    changed = skipped = 0
    for row in rows:
        if _clean(row.get("record-type")) != "Item":
            continue
        asin = (_clean(row.get("item-ASIN")) or "").upper()
        raw_volume = _clean(row.get("item-position-in-series"))
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


def _import_reading(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        asin = (_clean(row.get("ASIN")) or "").upper()
        try:
            totals[asin] += int(_clean(row.get("total_reading_milliseconds")) or "0")
        except ValueError:
            continue
    return _update_existing(conn, totals, "total_reading_ms")


def _import_last_read(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    latest: dict[str, str] = {}
    for row in rows:
        if _clean(row.get("Annotation Type")) != "kindle.last_read":
            continue
        asin = (_clean(row.get("ASIN")) or "").upper()
        timestamp = _timestamp(row.get("Customer modified date on device"))
        if asin and timestamp and timestamp > latest.get(asin, ""):
            latest[asin] = timestamp
    changed = skipped = 0
    for asin, timestamp in latest.items():
        if not _book_exists(conn, asin):
            skipped += 1
            continue
        conn.execute(
            """
            UPDATE books SET last_read_at=?
            WHERE asin=? AND (last_read_at IS NULL OR last_read_at < ?)
            """,
            (timestamp, asin, timestamp),
        )
        changed += 1
    return changed, skipped


def _import_completed(conn: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    asins = {asin for row in rows if (asin := (_clean(row.get("file_auto_marked_as_read")) or "").upper())}
    return _update_existing(conn, {asin: 1 for asin in asins}, "is_completed")


def _update_existing(conn: Any, values: dict[str, int], column: str) -> tuple[int, int]:
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


_KINDLE_INFO_HANDLERS = {
    "acquisition_dates": _import_acquisition_dates,
    "genres": _import_genres,
    "authors": _import_authors,
    "volumes": _import_volumes,
    "reading": _import_reading,
    "last_read": _import_last_read,
    "completed": _import_completed,
}


def _start_run(source_kind: str) -> int:
    with with_db() as conn:
        return conn.execute(
            """
            INSERT INTO import_runs(
                source_kind,status,started_at,files_processed,records_processed,records_skipped
            ) VALUES (?,'running',?,0,0,0)
            """,
            (source_kind, jst_now().isoformat()),
        ).lastrowid


def _finish_run(
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


def run_kindle_info_import() -> dict[str, Any]:
    run_id = _start_run("kindle_info")
    files_processed = files_skipped = records = missing_asins = 0
    results: list[dict[str, Any]] = []
    try:
        for filename, kind in _KINDLE_INFO_FILES.items():
            for path in _find_exact(filename):
                digest = _sha256(path)
                with with_db() as conn:
                    if _is_imported(conn, f"kindle_info:{kind}", path, digest):
                        files_skipped += 1
                        results.append({"filename": path.name, "kind": kind, "status": "skipped", "records": 0})
                        continue
                    rows = _read_csv(path)
                    count, skipped = _KINDLE_INFO_HANDLERS[kind](conn, rows)
                    _record_file(conn, f"kindle_info:{kind}", path, digest, count)
                    files_processed += 1
                    records += count
                    missing_asins += skipped
                    results.append({"filename": path.name, "kind": kind, "status": "success", "records": count})
    except Exception as exc:
        _finish_run(run_id, status="failed", error=str(exc))
        raise
    _finish_run(
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


def _collection_map() -> dict[str, list[str]]:
    paths = _find_exact("Kindle.SagaSeriesInfra.CollectionRightsDatastore.csv")
    if not paths:
        return {}
    result: dict[str, list[str]] = defaultdict(list)
    for row in _read_csv(paths[0]):
        if _clean(row.get("record-type")) != "Item":
            continue
        series_asin = (_clean(row.get("series-ASIN")) or "").upper()
        item_asin = (_clean(row.get("item-ASIN")) or "").upper()
        if series_asin and item_asin:
            result[series_asin].append(item_asin)
    return dict(result)


def run_autobuy_import() -> dict[str, Any]:
    paths = _find_exact(_AUTOBUY_FILENAME)
    if not paths:
        raise ValueError(f"{_AUTOBUY_FILENAME} が AMAZON_DATA_DIR 配下に見つかりません")
    path = paths[0]
    digest = _sha256(path)
    run_id = _start_run("autobuy")
    try:
        with with_db() as conn:
            if _is_imported(conn, "autobuy", path, digest):
                _finish_run(run_id, status="succeeded", skipped=1)
                return {
                    "run_id": run_id,
                    "status": "succeeded",
                    "files_processed": 0,
                    "files_skipped": 1,
                    "records_processed": 0,
                    "records_skipped": 0,
                    "files": [
                        {
                            "filename": path.name,
                            "kind": "autobuy",
                            "status": "skipped",
                            "records": 0,
                        }
                    ],
                }
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            items = payload.get("items")
            if not isinstance(items, list):
                raise ValueError("自動購入 JSON の items が配列ではありません")
            collection = _collection_map()
            asin_to_series = {
                row["asin"]: row["series_id"] for row in conn.execute("SELECT asin,series_id FROM book_series")
            }
            names: dict[str, int | None] = {}
            for row in conn.execute("SELECT id,name FROM series"):
                key = normalize_title(row["name"]).casefold()
                names[key] = row["id"] if key not in names else None
            subscriptions: list[tuple[str, str, str, int | None, str | None, str]] = []
            excluded = unresolved = 0
            seen: set[str] = set()
            for raw in items:
                if not isinstance(raw, dict):
                    excluded += 1
                    continue
                title = _clean(raw.get("title")) or ""
                series_asin = (_clean(raw.get("series_asin")) or "").upper()
                if not series_asin or series_asin in seen or title.startswith("Amazon"):
                    excluded += 1
                    continue
                seen.add(series_asin)
                votes = Counter(
                    asin_to_series[asin] for asin in collection.get(series_asin, []) if asin in asin_to_series
                )
                if votes:
                    series_id, method = votes.most_common(1)[0][0], "collection_rights"
                else:
                    series_id = names.get(normalize_title(title).casefold())
                    method = "title_match" if series_id is not None else None
                unresolved += int(series_id is None)
                subscriptions.append(
                    (
                        series_asin,
                        _clean(raw.get("subscription_id")) or "",
                        title,
                        series_id,
                        method,
                        jst_now().isoformat(),
                    )
                )
            conn.execute("DELETE FROM series_subscriptions")
            conn.executemany(
                """
                INSERT INTO series_subscriptions(
                    series_asin,subscription_id,title,series_id,resolution_method,imported_at
                ) VALUES (?,?,?,?,?,?)
                """,
                subscriptions,
            )
            _record_file(conn, "autobuy", path, digest, len(subscriptions))
        _finish_run(
            run_id,
            status="succeeded",
            files=1,
            records=len(subscriptions),
            skipped=excluded,
        )
    except Exception as exc:
        _finish_run(run_id, status="failed", error=str(exc))
        raise
    return {
        "run_id": run_id,
        "status": "succeeded",
        "files_processed": 1,
        "files_skipped": 0,
        "records_processed": len(subscriptions),
        "records_skipped": excluded,
        "unresolved": unresolved,
        "files": [
            {
                "filename": path.name,
                "kind": "autobuy",
                "status": "success",
                "records": len(subscriptions),
            }
        ],
    }
