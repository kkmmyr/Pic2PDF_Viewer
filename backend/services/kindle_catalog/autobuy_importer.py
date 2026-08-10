"""Kindleシリーズ自動購入JSONの全量置換importer。"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from services._title_normalizer import normalize_title
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.enrichment_files import (
    AUTOBUY_FILENAME,
    clean,
    find_exact,
    is_imported,
    read_csv,
    record_file,
    sha256_file,
)
from services.kindle_catalog.import_run_lifecycle import (
    fail_import_run,
    finish_import_run,
    start_import_run,
)
from utils.dt import jst_now


def _collection_map() -> dict[str, list[str]]:
    paths = find_exact("Kindle.SagaSeriesInfra.CollectionRightsDatastore.csv")
    if not paths:
        return {}
    result: dict[str, list[str]] = defaultdict(list)
    for row in read_csv(paths[0]):
        if clean(row.get("record-type")) != "Item":
            continue
        series_asin = (clean(row.get("series-ASIN")) or "").upper()
        item_asin = (clean(row.get("item-ASIN")) or "").upper()
        if series_asin and item_asin:
            result[series_asin].append(item_asin)
    return dict(result)


def _subscription_rows(
    conn: Any,
    items: list[object],
) -> tuple[list[tuple[str, str, str, int | None, str | None, str]], int, int]:
    collection = _collection_map()
    asin_to_series = {row["asin"]: row["series_id"] for row in conn.execute("SELECT asin,series_id FROM book_series")}
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
        title = clean(raw.get("title")) or ""
        series_asin = (clean(raw.get("series_asin")) or "").upper()
        if not series_asin or series_asin in seen or title.startswith("Amazon"):
            excluded += 1
            continue
        seen.add(series_asin)
        votes = Counter(asin_to_series[asin] for asin in collection.get(series_asin, []) if asin in asin_to_series)
        if votes:
            series_id, method = votes.most_common(1)[0][0], "collection_rights"
        else:
            series_id = names.get(normalize_title(title).casefold())
            method = "title_match" if series_id is not None else None
        unresolved += int(series_id is None)
        subscriptions.append(
            (
                series_asin,
                clean(raw.get("subscription_id")) or "",
                title,
                series_id,
                method,
                jst_now().isoformat(),
            )
        )
    return subscriptions, excluded, unresolved


def _skipped_result(run_id: int, filename: str) -> dict[str, Any]:
    finish_import_run(run_id, status="succeeded", skipped=1)
    return {
        "run_id": run_id,
        "status": "succeeded",
        "files_processed": 0,
        "files_skipped": 1,
        "records_processed": 0,
        "records_skipped": 0,
        "files": [
            {
                "filename": filename,
                "kind": "autobuy",
                "status": "skipped",
                "records": 0,
            }
        ],
    }


def run_autobuy_import() -> dict[str, Any]:
    paths = find_exact(AUTOBUY_FILENAME)
    if not paths:
        raise ValueError(f"{AUTOBUY_FILENAME} が AMAZON_DATA_DIR 配下に見つかりません")
    path = paths[0]
    digest = sha256_file(path)
    run_id = start_import_run("autobuy")
    try:
        with with_db() as conn:
            if is_imported(conn, "autobuy", path, digest):
                return _skipped_result(run_id, path.name)
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            items = payload.get("items")
            if not isinstance(items, list):
                raise ValueError("自動購入 JSON の items が配列ではありません")
            subscriptions, excluded, unresolved = _subscription_rows(conn, items)
            conn.execute("DELETE FROM series_subscriptions")
            conn.executemany(
                """
                INSERT INTO series_subscriptions(
                    series_asin,subscription_id,title,series_id,
                    resolution_method,imported_at
                ) VALUES (?,?,?,?,?,?)
                """,
                subscriptions,
            )
            record_file(conn, "autobuy", path, digest, len(subscriptions))
        finish_import_run(
            run_id,
            status="succeeded",
            files=1,
            records=len(subscriptions),
            skipped=excluded,
        )
    except Exception as exc:
        fail_import_run(run_id, exc)
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
