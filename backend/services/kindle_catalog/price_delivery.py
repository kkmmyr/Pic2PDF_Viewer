"""Persist pending Kindle price events and deliver them at least once."""

from __future__ import annotations

import sqlite3

from services.kindle_catalog import price_notify
from services.kindle_catalog.connection import with_db
from utils.dt import jst_now


def _now() -> str:
    return jst_now().isoformat(timespec="seconds")


def queue_notification_events(
    conn: sqlite3.Connection,
    *,
    watch_id: int,
    observation_id: int,
    kinds: list[str],
) -> None:
    for kind in kinds:
        conn.execute(
            """
            INSERT OR IGNORE INTO kindle_price_notifications(
                watch_id, observation_id, kind, notified_at
            ) VALUES (?, ?, ?, NULL)
            """,
            (watch_id, observation_id, kind),
        )


def _pending_notification_rows(watch_id: int) -> list[sqlite3.Row]:
    with with_db() as conn:
        return conn.execute(
            """
            SELECT n.observation_id, n.kind,
                   w.title, w.asin, w.url,
                   o.current_price, o.points, o.effective_price,
                   o.list_price, o.list_price_source, o.ratio_percent,
                   (
                       SELECT previous.effective_price
                       FROM kindle_price_observations AS previous
                       WHERE previous.watch_id = o.watch_id
                         AND previous.id < o.id
                         AND previous.effective_price IS NOT NULL
                         AND previous.status IN ('ok', 'partial')
                       ORDER BY previous.id DESC
                       LIMIT 1
                   ) AS previous_price
            FROM kindle_price_notifications AS n
            JOIN kindle_price_observations AS o ON o.id = n.observation_id
            JOIN kindle_price_watches AS w ON w.id = n.watch_id
            WHERE n.watch_id = ? AND n.notified_at IS NULL
            ORDER BY n.observation_id ASC, n.id ASC
            """,
            (watch_id,),
        ).fetchall()


def _mark_notifications_sent(watch_id: int, observation_id: int, kinds: list[str]) -> None:
    placeholders = ", ".join("?" for _ in kinds)
    with with_db() as conn:
        conn.execute(
            f"""
            UPDATE kindle_price_notifications
            SET notified_at = ?
            WHERE watch_id = ? AND observation_id = ?
              AND kind IN ({placeholders}) AND notified_at IS NULL
            """,
            (_now(), watch_id, observation_id, *kinds),
        )


def send_pending_notifications(watch_id: int) -> list[dict[str, object]]:
    pending_by_observation: dict[int, tuple[sqlite3.Row, list[str]]] = {}
    for row in _pending_notification_rows(watch_id):
        observation_id = int(row["observation_id"])
        if observation_id not in pending_by_observation:
            pending_by_observation[observation_id] = (row, [])
        pending_by_observation[observation_id][1].append(str(row["kind"]))

    results: list[dict[str, object]] = []
    for observation_id, (row, kinds) in pending_by_observation.items():
        sent = price_notify.notify_price_event(
            title=row["title"],
            asin=row["asin"],
            url=row["url"],
            current_price=row["current_price"],
            points=row["points"],
            effective_price=row["effective_price"],
            list_price=row["list_price"],
            list_price_source=row["list_price_source"],
            ratio_percent=row["ratio_percent"],
            previous_price=row["previous_price"],
            kinds=kinds,
        )
        if sent:
            _mark_notifications_sent(watch_id, observation_id, kinds)
        results.extend({"kind": kind, "sent": sent} for kind in kinds)
    return results
