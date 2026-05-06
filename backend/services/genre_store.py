"""
ジャンルリストの永続化サービス。

保存先: backend/data/genres/{source}.json
形式: ["ジャンルA", "ジャンルB", ...]（順序付き文字列配列）

ファイルが存在しない場合は meta.json の genre フィールドを収集して初期リストを生成する
（migration 用途）。並び順は UI からの `PATCH /api/genres/reorder` で更新される。

ロック: `SourceLockManager` で source 単位に直列化。`load_genres` も
`save_genres` もロック取得下で実行される（読み書きの整合性を保つため）。
"""
import json
import os

from config import DATA_DIR
from services.meta_store import load_meta
from utils.locks import SourceLockManager

GENRE_STORE_DIR = os.path.join(DATA_DIR, "genres")

_lock_manager = SourceLockManager()


def _store_path(source: str) -> str:
    return os.path.join(GENRE_STORE_DIR, f"{source}.json")


def _derive_from_meta(source: str) -> list[str]:
    """meta.json の genre フィールドを収集して名前順にソートした初期リストを返す。

    `genres/{source}.json` 不在時の初回読み込みでのみ呼ばれる migration 用途。
    並び順は UI 側で並び替え後に保存されるので、ここでは単純にソートするだけでよい。
    """
    meta = load_meta(source)
    found: set[str] = set()
    for entry in meta.values():
        g = entry.get("genre")
        if g and isinstance(g, str):
            found.add(g)
    return sorted(found)


def _write_genres_unlocked(source: str, genres: list[str]) -> None:
    """ロック取得済み前提で genres を書き込む。"""
    os.makedirs(GENRE_STORE_DIR, exist_ok=True)
    path = _store_path(source)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(genres, f, ensure_ascii=False, indent=2)


def load_genres(source: str) -> list[str]:
    """genres.json を読み込む。未作成の場合は meta.json から初期リストを生成して保存する。"""
    with _lock_manager.get(source):
        path = _store_path(source)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        genres = _derive_from_meta(source)
        _write_genres_unlocked(source, genres)
        return genres


def save_genres(source: str, genres: list[str]) -> None:
    """genres.json にジャンルリストを書き込む。"""
    with _lock_manager.get(source):
        _write_genres_unlocked(source, genres)
