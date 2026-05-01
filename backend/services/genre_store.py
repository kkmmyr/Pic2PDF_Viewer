"""
ジャンルリストの永続化サービス。

保存先: backend/data/genres/{source}.json
形式: ["ジャンルA", "ジャンルB", ...]（順序付き文字列配列）

ファイルが存在しない場合は meta.json の genre フィールドを収集して初期リストを生成する。
"""
import json
import os
import threading

from config import DATA_DIR
from services.meta_store import load_meta

GENRE_STORE_DIR = os.path.join(DATA_DIR, "genres")

_GENRE_ORDER = ["オリジナル", "プリンセスコネクト", "Voiceloid"]

_locks: dict[str, threading.Lock] = {}
_locks_mutex = threading.Lock()


def _get_lock(source: str) -> threading.Lock:
    with _locks_mutex:
        if source not in _locks:
            _locks[source] = threading.Lock()
        return _locks[source]


def _store_path(source: str) -> str:
    return os.path.join(GENRE_STORE_DIR, f"{source}.json")


def _derive_from_meta(source: str) -> list[str]:
    """meta.json の genre フィールドを収集して GENRE_ORDER 順に並べた初期リストを返す。"""
    meta = load_meta(source)
    found: set[str] = set()
    for entry in meta.values():
        g = entry.get("genre")
        if g and isinstance(g, str):
            found.add(g)
    ordered = [g for g in _GENRE_ORDER if g in found]
    rest = sorted(found - set(ordered), key=lambda x: x)
    return ordered + rest


def load_genres(source: str) -> list[str]:
    """genres.json を読み込む。未作成の場合は meta.json から初期リストを生成して保存する。"""
    path = _store_path(source)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    genres = _derive_from_meta(source)
    save_genres(source, genres)
    return genres


def save_genres(source: str, genres: list[str]) -> None:
    """genres.json にジャンルリストを書き込む。"""
    os.makedirs(GENRE_STORE_DIR, exist_ok=True)
    with _get_lock(source):
        path = _store_path(source)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(genres, f, ensure_ascii=False, indent=2)
