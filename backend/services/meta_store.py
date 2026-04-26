"""meta.json の読み書き・ロック管理。

詳細仕様: docs/03_詳細設計/詳細設計書.md「閲覧回数ソート（よく見る順）」節
"""
import json
import os
import threading
from typing import Callable, NotRequired, TypedDict
from config import DATA_DIR


class MetaEntry(TypedDict):
    authors: list[str]
    # 閲覧回数。既存エントリには含まれない場合があるため任意。
    view_count: NotRequired[int]
    # 最終閲覧時刻 (UNIX time, float)。
    last_viewed_at: NotRequired[float]


MetaDict = dict[str, MetaEntry]

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def get_lock(source: str) -> threading.Lock:
    with _locks_lock:
        if source not in _locks:
            _locks[source] = threading.Lock()
        return _locks[source]


def meta_path(source: str) -> str:
    meta_dir = os.path.join(DATA_DIR, "meta", source)
    os.makedirs(meta_dir, exist_ok=True)
    return os.path.join(meta_dir, "meta.json")


def load_meta(source: str) -> MetaDict:
    path = meta_path(source)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_meta(source: str, data: MetaDict) -> None:
    path = meta_path(source)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_key(path: str, name: str) -> str:
    return f"{path}/{name}" if path else name


def update_meta_locked(source: str, updater: Callable[[MetaDict], None]) -> None:
    """ロックを取得してから meta.json を読み込み、updater を適用して保存する。"""
    with get_lock(source):
        meta = load_meta(source)
        updater(meta)
        save_meta(source, meta)
