"""meta.json の読み書き・ロック管理。"""
import json
import os
import threading
from config import DATA_DIR

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


def load_meta(source: str) -> dict:
    path = meta_path(source)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_meta(source: str, data: dict) -> None:
    path = meta_path(source)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_key(path: str, name: str) -> str:
    return f"{path}/{name}" if path else name
