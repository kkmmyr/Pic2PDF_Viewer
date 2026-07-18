"""hitomi.la 監視の永続状態（state.json / new_arrivals.json）の管理。

- state.json: 各作者の前回 top_id と監視ジョブのヘルス情報
- new_arrivals.json: 検出済み新着の累積（dismissed フラグで既読管理）
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict

from utils.atomic_json import atomic_write_json


class ArtistState(TypedDict, total=False):
    top_id: int
    checked_at: str


class State(TypedDict, total=False):
    last_run_at: str | None
    last_run_status: str  # ok / partial / error / never
    last_error: str | None
    last_run_stats: dict[str, int]
    artists: dict[str, ArtistState]


class ArrivalItem(TypedDict, total=False):
    id: int
    artist: str
    display_artist: str
    title: str
    language: str
    type: str
    page_count: int
    published_at: str
    discovered_at: str
    url: str
    dismissed: bool


class Arrivals(TypedDict):
    items: list[ArrivalItem]


def _state_path(data_dir: Path) -> Path:
    return data_dir / "state.json"


def _arrivals_path(data_dir: Path) -> Path:
    return data_dir / "new_arrivals.json"


def _empty_state() -> State:
    return {
        "last_run_at": None,
        "last_run_status": "never",
        "last_error": None,
        "artists": {},
    }


def load_state(data_dir: Path) -> State:
    path = _state_path(data_dir)
    if not path.exists():
        return _empty_state()
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    data.setdefault("artists", {})
    data.setdefault("last_run_status", "never")
    return data  # type: ignore[return-value]


def save_state(data_dir: Path, state: State) -> None:
    path = _state_path(data_dir)
    atomic_write_json(path, state)


def load_arrivals(data_dir: Path) -> Arrivals:
    path = _arrivals_path(data_dir)
    if not path.exists():
        return {"items": []}
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    items = data.get("items", [])
    if not isinstance(items, list):
        items = []
    return {"items": items}


def save_arrivals(data_dir: Path, arrivals: Arrivals) -> None:
    path = _arrivals_path(data_dir)
    atomic_write_json(path, arrivals)


def merge_new_items(data_dir: Path, new_items: list[ArrivalItem]) -> int:
    """new_arrivals.json に追加。同 id の重複は無視。追加件数を返す。"""
    if not new_items:
        return 0
    arrivals = load_arrivals(data_dir)
    existing_ids = {item["id"] for item in arrivals["items"] if "id" in item}
    added = 0
    for item in new_items:
        gid = item.get("id")
        if gid is None or gid in existing_ids:
            continue
        arrivals["items"].append(item)
        existing_ids.add(gid)
        added += 1
    if added > 0:
        save_arrivals(data_dir, arrivals)
    return added


def dismiss(data_dir: Path, gallery_id: int) -> bool:
    """指定 ID を既読化する。該当があれば True。"""
    arrivals = load_arrivals(data_dir)
    found = False
    for item in arrivals["items"]:
        if item.get("id") == gallery_id and not item.get("dismissed"):
            item["dismissed"] = True
            found = True
    if found:
        save_arrivals(data_dir, arrivals)
    return found


def dismiss_all(data_dir: Path) -> int:
    """未既読の全件を既読化する。既読化した件数を返す。"""
    arrivals = load_arrivals(data_dir)
    count = 0
    for item in arrivals["items"]:
        if not item.get("dismissed"):
            item["dismissed"] = True
            count += 1
    if count > 0:
        save_arrivals(data_dir, arrivals)
    return count


def purge_expired(
    data_dir: Path,
    threshold_days: int = 30,
    *,
    now: datetime | None = None,
) -> int:
    """dismissed=true かつ discovered_at が threshold_days 以前のエントリを物理削除する。"""
    if now is None:
        now = datetime.now(UTC)
    threshold = now - timedelta(days=threshold_days)

    arrivals = load_arrivals(data_dir)
    kept: list[ArrivalItem] = []
    removed = 0
    for item in arrivals["items"]:
        if not item.get("dismissed"):
            kept.append(item)
            continue
        discovered_str = item.get("discovered_at")
        if not discovered_str:
            kept.append(item)
            continue
        try:
            discovered = datetime.fromisoformat(discovered_str)
        except ValueError:
            kept.append(item)
            continue
        # naive datetime はローカルタイムとみなして比較可能にする
        if discovered.tzinfo is None:
            discovered = discovered.replace(tzinfo=UTC)
        if discovered < threshold:
            removed += 1
        else:
            kept.append(item)

    if removed > 0:
        save_arrivals(data_dir, {"items": kept})
    return removed
