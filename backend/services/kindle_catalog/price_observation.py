"""Kindle 価格観測の保存・判定・通知サービス。"""

from __future__ import annotations

import sqlite3

from services.kindle_catalog import price_notify
from services.kindle_catalog.connection import with_db
from utils.dt import jst_now

_STATUSES = {"ok", "partial", "failed"}
_SOURCES = {"codex_browser", "manual"}


def _now() -> str:
    return jst_now().isoformat(timespec="seconds")


def _price(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} は0以上の整数またはnullで指定してください")
    return value


def _get_watch_row(conn: sqlite3.Connection, watch_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM kindle_price_watches WHERE id = ?", (watch_id,)).fetchone()


def _resolve_status(current: int | None, listed: int | None, status: str | None) -> str:
    if status is None:
        if current is not None and listed is not None and listed > 0:
            status = "ok"
        elif current is not None or listed is not None:
            status = "partial"
        else:
            status = "failed"
    if status not in _STATUSES:
        raise ValueError(f"status は {', '.join(sorted(_STATUSES))} のいずれかで指定してください")
    return status


def _prepare_observation(
    current_price: int | None,
    list_price: int | None,
    status: str | None,
    error_message: str | None,
    source: str,
    title: str | None,
) -> tuple[int | None, int | None, str, str | None]:
    current = _price(current_price, "current_price")
    listed = _price(list_price, "list_price")
    if source not in _SOURCES:
        raise ValueError(f"source は {', '.join(sorted(_SOURCES))} のいずれかで指定してください")
    status = _resolve_status(current, listed, status)
    if error_message is not None and not isinstance(error_message, str):
        raise ValueError("error_message は文字列またはnullで指定してください")
    if title is not None and not isinstance(title, str):
        raise ValueError("title は文字列またはnullで指定してください")
    return current, listed, status, title.strip() if title else None


def _ratio_percent(current: int | None, listed: int | None, status: str) -> float | None:
    if status != "ok" or current is None or listed is None or listed <= 0:
        return None
    return current / listed * 100


def _persist_observation(
    conn: sqlite3.Connection,
    *,
    watch_id: int,
    observed_at: str,
    current: int | None,
    listed: int | None,
    ratio: float | None,
    status: str,
    error_message: str | None,
    source: str,
    normalized_title: str | None,
) -> tuple[sqlite3.Row, sqlite3.Row | None, int]:
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
    if cursor.lastrowid is None:
        raise RuntimeError("価格観測の登録IDを取得できません")
    observation_id = int(cursor.lastrowid)
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
    return watch, previous, observation_id


def _event_flags(
    watch: sqlite3.Row,
    *,
    current: int | None,
    ratio: float | None,
    status: str,
    previous: sqlite3.Row | None,
) -> tuple[bool, bool]:
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
    return price_dropped, crossed_threshold


def _notification_kinds(watch: sqlite3.Row, price_dropped: bool, crossed_threshold: bool) -> list[str]:
    kinds: list[str] = []
    if bool(watch["notify_on_drop"]) and price_dropped:
        kinds.append("price_drop")
    if bool(watch["notify_below_threshold"]) and crossed_threshold:
        kinds.append("below_threshold")
    return kinds


def _send_notifications(
    watch: sqlite3.Row,
    *,
    watch_id: int,
    observation_id: int,
    current: int | None,
    listed: int | None,
    ratio: float | None,
    previous: sqlite3.Row | None,
    normalized_title: str | None,
    kinds: list[str],
) -> list[dict[str, object]]:
    notification_results = [{"kind": kind, "sent": False} for kind in kinds]
    if not kinds:
        return notification_results
    sent = price_notify.notify_price_event(
        title=normalized_title or watch["title"],
        asin=watch["asin"],
        url=watch["url"],
        current_price=current,
        list_price=listed,
        ratio_percent=ratio,
        previous_price=previous["current_price"] if previous else None,
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
    return [{"kind": kind, "sent": sent} for kind in kinds]


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
    current, listed, status, normalized_title = _prepare_observation(
        current_price,
        list_price,
        status,
        error_message,
        source,
        title,
    )
    ratio = _ratio_percent(current, listed, status)
    observed_at = _now()
    with with_db() as conn:
        watch, previous, observation_id = _persist_observation(
            conn,
            watch_id=watch_id,
            observed_at=observed_at,
            current=current,
            listed=listed,
            ratio=ratio,
            status=status,
            error_message=error_message,
            source=source,
            normalized_title=normalized_title,
        )

    price_dropped, crossed_threshold = _event_flags(
        watch,
        current=current,
        ratio=ratio,
        status=status,
        previous=previous,
    )
    kinds = _notification_kinds(watch, price_dropped, crossed_threshold)
    notification_results = _send_notifications(
        watch,
        watch_id=watch_id,
        observation_id=observation_id,
        current=current,
        listed=listed,
        ratio=ratio,
        previous=previous,
        normalized_title=normalized_title,
        kinds=kinds,
    )
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
