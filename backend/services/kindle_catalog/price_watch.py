"""Kindle 価格監視の CRUD・観測記録サービス。

Amazon のページ取得はこのモジュールでは行わない。Codex のブラウザが読み取った
表示価格を CLI/API から受け取り、履歴・判定・Discord 通知を担当する。
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from urllib.parse import urlsplit

from services.kindle_catalog import price_notify
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
_STATUSES = {"ok", "partial", "failed"}
_SOURCES = {"codex_browser", "manual"}
_NOTIFICATION_KINDS = {"price_drop", "below_threshold"}


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


def _price(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} は0以上の整数またはnullで指定してください")
    return value


def _get_watch_row(conn, watch_id: int):
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
    return _watch_from_row(row)


def update_watch(watch_id: int, changes: Mapping[str, object]) -> dict:
    if not changes:
        return get_watch(watch_id)
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
        title = changes["title"]
        if title is not None and not isinstance(title, str):
            raise ValueError("title は文字列またはnullで指定してください")
        normalized_title = title.strip() if isinstance(title, str) else None
        if normalized_title and len(normalized_title) > 500:
            raise ValueError("title は500文字以内で指定してください")
        assignments.append("title = ?")
        params.append(normalized_title)
    if "threshold_percent" in changes:
        assignments.append("threshold_percent = ?")
        params.append(_threshold(changes["threshold_percent"]))
    for name in ("notify_on_drop", "notify_below_threshold", "enabled"):
        if name in changes:
            assignments.append(f"{name} = ?")
            params.append(_as_bool(changes[name], name))

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


def record_observation(
    *,
    watch_id: int,
    current_price: int | None,
    list_price: int | None,
    status: str | None = None,
    error_message: str | None = None,
    source: str = "codex_browser",
    title: str | None = None,
) -> dict:
    """Codex ブラウザの1回分の読み取りを保存し、必要なら通知する。"""
    current = _price(current_price, "current_price")
    listed = _price(list_price, "list_price")
    if source not in _SOURCES:
        raise ValueError(f"source は {', '.join(sorted(_SOURCES))} のいずれかで指定してください")
    if status is None:
        if current is not None and listed is not None and listed > 0:
            status = "ok"
        elif current is not None or listed is not None:
            status = "partial"
        else:
            status = "failed"
    if status not in _STATUSES:
        raise ValueError(f"status は {', '.join(sorted(_STATUSES))} のいずれかで指定してください")
    if error_message is not None and not isinstance(error_message, str):
        raise ValueError("error_message は文字列またはnullで指定してください")
    if title is not None and not isinstance(title, str):
        raise ValueError("title は文字列またはnullで指定してください")
    normalized_title = title.strip() if title else None

    ratio = (
        current / listed * 100 if status == "ok" and current is not None and listed is not None and listed > 0 else None
    )
    observed_at = _now()
    with with_db() as conn:
        watch = _get_watch_row(conn, watch_id)
        if watch is None:
            raise KeyError(f"価格監視 {watch_id} が見つかりません")
        previous = conn.execute(
            """
            SELECT current_price, list_price, ratio_percent
            FROM kindle_price_observations
            WHERE watch_id = ? AND current_price IS NOT NULL AND status IN ('ok', 'partial')
            ORDER BY id DESC LIMIT 1
            """,
            (watch_id,),
        ).fetchone()
        cursor = conn.execute(
            """
            INSERT INTO kindle_price_observations(
                watch_id, observed_at, current_price, list_price,
                ratio_percent, status, error_message, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (watch_id, observed_at, current, listed, ratio, status, error_message, source),
        )
        observation_id = require_lastrowid(cursor.lastrowid, "価格観測の作成IDを取得できませんでした")
        assignments = [
            "updated_at = ?",
            "last_checked_at = ?",
            "last_status = ?",
            "last_error = ?",
            "last_current_price = ?",
            "last_list_price = ?",
            "last_ratio_percent = ?",
        ]
        params: list[object] = [observed_at, observed_at, status, error_message, current, listed, ratio]
        if normalized_title:
            assignments.append("title = ?")
            params.append(normalized_title)
        params.append(watch_id)
        conn.execute(
            f"UPDATE kindle_price_watches SET {', '.join(assignments)} WHERE id = ?",
            params,
        )

    previous_price = previous["current_price"] if previous else None
    previous_ratio = previous["ratio_percent"] if previous else None
    price_dropped = (
        status in {"ok", "partial"} and current is not None and previous_price is not None and current < previous_price
    )
    crossed_threshold = (
        ratio is not None
        and ratio < float(watch["threshold_percent"])
        and (previous_ratio is None or previous_ratio >= float(watch["threshold_percent"]))
    )
    kinds: list[str] = []
    if bool(watch["notify_on_drop"]) and price_dropped:
        kinds.append("price_drop")
    if bool(watch["notify_below_threshold"]) and crossed_threshold:
        kinds.append("below_threshold")

    notification_results = [{"kind": kind, "sent": False} for kind in kinds]
    if kinds:
        sent = price_notify.notify_price_event(
            title=normalized_title or watch["title"],
            asin=watch["asin"],
            url=watch["url"],
            current_price=current,
            list_price=listed,
            ratio_percent=ratio,
            previous_price=previous_price,
            kinds=kinds,
        )
        if sent:
            notified_at = _now()
            with with_db() as conn:
                for kind in kinds:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO kindle_price_notifications(
                            watch_id, observation_id, kind, notified_at
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (watch_id, observation_id, kind, notified_at),
                    )
        notification_results = [{"kind": kind, "sent": sent} for kind in kinds]

    return {
        "observation": {
            "id": observation_id,
            "watch_id": watch_id,
            "observed_at": observed_at,
            "current_price": current,
            "list_price": listed,
            "ratio_percent": ratio,
            "status": status,
            "error_message": error_message,
            "source": source,
        },
        "price_dropped": price_dropped,
        "below_threshold": status == "ok" and ratio is not None and ratio < float(watch["threshold_percent"]),
        "notifications": notification_results,
    }
