"""hitomi.la 監視ジョブの永続状態（state.json）を管理する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from utils.atomic_json import atomic_write_json


class ArtistState(TypedDict, total=False):
    top_id: int
    checked_at: str
    pending_gallery_ids: list[int]


class State(TypedDict, total=False):
    last_run_at: str | None
    last_run_status: str  # ok / partial / error / never
    last_error: str | None
    last_run_stats: dict[str, int]
    artists: dict[str, ArtistState]


def _state_path(data_dir: Path) -> Path:
    return data_dir / "state.json"


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
