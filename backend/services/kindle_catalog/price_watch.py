"""Kindle 価格監視の CRUD・観測記録サービス。

Amazon のページ取得はこのモジュールでは行わない。Codex のブラウザが読み取った
表示価格を CLI/API から受け取り、履歴・判定・Discord 通知を担当する。
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from urllib.parse import urlsplit

from services.kindle_catalog import price_observation
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.price_watch_rows import (
    observation_from_row as _observation_from_row,
)
from services.kindle_catalog.price_watch_rows import (
    require_lastrowid,
)
from services.kindle_catalog.price_watch_rows import (
    watch_from_row as _watch_from_row,
)
from utils.dt import jst_now

_ASIN_RE = re.compile(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})(?:[/?#]|$)", re.IGNORECASE)
_ALLOWED_HOSTS = {"amazon.co.jp", "www.amazon.co.jp"}

record_observation = price_observation.record_observation
price_notify = price_observation.price_notify


def normalize_amazon_url(url: str) -> tuple[str, str]:
    """Amazon.co.jp Kindle 商品 URL を正規化し、URL と ASIN を返す。"""
    value = url.strip()
    if not value:
        raise ValueError("Amazon URL を入力してください")
    parsed = urlsplit(value)
    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Amazon.co.jp の URL の形式が不正です") from exc
    if parsed.scheme.lower() != "https" or hostname is None:
        raise ValueError("https://www.amazon.co.jp/ の商品 URL を指定してください")
    if hostname.lower() not in _ALLOWED_HOSTS or port is not None:
        raise ValueError("Amazon.co.jp の URL のみ登録できます")
    match = _ASIN_RE.search(parsed.path)
    if match is None:
        raise ValueError("URL から Kindle 本の ASIN を取得できません（/dp/BXXXXXXXXX 形式）")
    asin = match.group(1).upper()
    return f"https://www.amazon.co.jp/dp/{asin}", asin


def _now() -> str:
    return jst_now().isoformat(timespec="seconds")


def _as_bool(value: object, field: str) -> int:
    if not isinstance(value, bool):
        raise ValueError(f"{field} は真偽値で指定してください")
    return int(value)


def _threshold(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("threshold_percent は数値で指定してください")
    numeric = float(value)
    if not 1 <= numeric <= 100:
        raise ValueError("threshold_percent は 1〜100 の範囲で指定してください")
    return numeric


def _normalize_update_title(value: object) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError("title は文字列またはnullで指定してください")
    normalized = value.strip() if isinstance(value, str) else None
    if normalized and len(normalized) > 500:
        raise ValueError("title は500文字以内で指定してください")
    return normalized


def _watch_update_assignments(changes: Mapping[str, object]) -> tuple[list[str], list[object]]:
    allowed = {
        "url",
        "title",
        "threshold_percent",
        "notify_on_drop",
        "notify_below_threshold",
        "enabled",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"更新できない項目: {', '.join(sorted(unknown))}")

    assignments: list[str] = []
    params: list[object] = []
    if "url" in changes:
        normalized_url, asin = normalize_amazon_url(str(changes["url"]))
        assignments.extend(("url = ?", "asin = ?"))
        params.extend((normalized_url, asin))
    if "title" in changes:
        assignments.append("title = ?")
        params.append(_normalize_update_title(changes["title"]))
    if "threshold_percent" in changes:
        assignments.append("threshold_percent = ?")
        params.append(_threshold(changes["threshold_percent"]))
    for name in ("notify_on_drop", "notify_below_threshold", "enabled"):
        if name in changes:
            assignments.append(f"{name} = ?")
            params.append(_as_bool(changes[name], name))
    return assignments, params


def _get_watch_row(conn: sqlite3.Connection, watch_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM kindle_price_watches WHERE id = ?", (watch_id,)).fetchone()


def list_watches() -> list[dict]:
    with with_db() as conn:
        rows = conn.execute("SELECT * FROM kindle_price_watches ORDER BY enabled DESC, id ASC").fetchall()
    return [_watch_from_row(row) for row in rows]


def get_watch(watch_id: int) -> dict:
    with with_db() as conn:
        row = _get_watch_row(conn, watch_id)
    if row is None:
        raise KeyError(f"価格監視 {watch_id} が見つかりません")
    return _watch_from_row(row)


def create_watch(
    *,
    url: str,
    title: str | None = None,
    threshold_percent: float = 50.0,
    notify_on_drop: bool = True,
    notify_below_threshold: bool = True,
    enabled: bool = True,
) -> dict:
    normalized_url, asin = normalize_amazon_url(url)
    threshold = _threshold(threshold_percent)
    drop = _as_bool(notify_on_drop, "notify_on_drop")
    below = _as_bool(notify_below_threshold, "notify_below_threshold")
    active = _as_bool(enabled, "enabled")
    normalized_title = title.strip() if title else None
    if normalized_title and len(normalized_title) > 500:
        raise ValueError("title は500文字以内で指定してください")
    now = _now()
    with with_db() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO kindle_price_watches(
                    url, asin, title, threshold_percent, notify_on_drop,
                    notify_below_threshold, enabled, created_at, updated_at,
                    last_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'never')
                """,
                (normalized_url, asin, normalized_title, threshold, drop, below, active, now, now),
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ValueError("同じ URL はすでに登録されています") from exc
            raise
        watch_id = require_lastrowid(cursor.lastrowid, "価格監視の作成IDを取得できませんでした")
        row = _get_watch_row(conn, watch_id)
        if row is None:
            raise RuntimeError("登録した価格監視を取得できません")
    return _watch_from_row(row)


def update_watch(watch_id: int, changes: Mapping[str, object]) -> dict:
    if not changes:
        return get_watch(watch_id)
    assignments, params = _watch_update_assignments(changes)

    assignments.append("updated_at = ?")
    params.extend((_now(), watch_id))
    with with_db() as conn:
        if _get_watch_row(conn, watch_id) is None:
            raise KeyError(f"価格監視 {watch_id} が見つかりません")
        try:
            conn.execute(
                f"UPDATE kindle_price_watches SET {', '.join(assignments)} WHERE id = ?",
                params,
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ValueError("同じ URL はすでに登録されています") from exc
            raise
        row = _get_watch_row(conn, watch_id)
        if row is None:
            raise KeyError(f"価格監視 {watch_id} が見つかりません")
    return _watch_from_row(row)


def delete_watch(watch_id: int) -> dict:
    with with_db() as conn:
        cursor = conn.execute("DELETE FROM kindle_price_watches WHERE id = ?", (watch_id,))
        if cursor.rowcount == 0:
            raise KeyError(f"価格監視 {watch_id} が見つかりません")
    return {"id": watch_id, "deleted": True}


def export_targets() -> list[dict]:
    """Codex ブラウザへ渡す有効な監視対象だけを返す。"""
    return [
        {
            "id": watch["id"],
            "url": watch["url"],
            "asin": watch["asin"],
            "title": watch["title"],
            "threshold_percent": watch["threshold_percent"],
        }
        for watch in list_watches()
        if watch["enabled"]
    ]


def list_history(watch_id: int, limit: int = 100) -> list[dict]:
    if limit < 1 or limit > 500:
        raise ValueError("limit は1〜500の範囲で指定してください")
    with with_db() as conn:
        if _get_watch_row(conn, watch_id) is None:
            raise KeyError(f"価格監視 {watch_id} が見つかりません")
        rows = conn.execute(
            """
            SELECT id, watch_id, observed_at, current_price, list_price,
                   ratio_percent, status, error_message, source
            FROM kindle_price_observations
            WHERE watch_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (watch_id, limit),
        ).fetchall()
    return [_observation_from_row(row) for row in rows]
