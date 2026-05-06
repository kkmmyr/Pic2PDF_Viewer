"""meta.json の読み書き・ロック管理。

詳細仕様: docs/03_詳細設計/詳細設計書_バックエンド編.md「閲覧回数 / 最近見た順ソート（バックエンド側）」節
"""
import json
import os
import threading
from collections.abc import Callable
from typing import NotRequired, TypedDict

from config import DATA_DIR
from utils.locks import SourceLockManager


class MetaEntry(TypedDict):
    authors: list[str]
    # タグ（自由ラベル）。既存エントリには含まれない場合があるため任意。
    tags: NotRequired[list[str]]
    # 閲覧回数。既存エントリには含まれない場合があるため任意。
    view_count: NotRequired[int]
    # 最終閲覧時刻 (UNIX time, float)。
    last_viewed_at: NotRequired[float]
    # 非表示フラグ。True なら通常モードでは一覧・検索・フィルタに表示されない。
    hidden: NotRequired[bool]
    # ジャンル（例: "プリンセスコネクト" / "Voiceloid" / "オリジナル"）。
    genre: NotRequired[str]


MetaDict = dict[str, MetaEntry]

_lock_manager = SourceLockManager()


def get_lock(source: str) -> threading.Lock:
    return _lock_manager.get(source)


def meta_path(source: str) -> str:
    meta_dir = os.path.join(DATA_DIR, "meta", source)
    os.makedirs(meta_dir, exist_ok=True)
    return os.path.join(meta_dir, "meta.json")


def load_meta(source: str) -> MetaDict:
    path = meta_path(source)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
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


def merge_entry_fields(
    entry: dict,
    *,
    authors: list[str] | None = None,
    tags: list[str] | None = None,
    hidden: bool | None = None,
    genre: str | None = None,
) -> dict:
    """部分的に指定されたフィールドだけを上書きしたエントリを返す（非破壊）。

    - `authors` / `tags`: list（空可）。`None` 指定なら変更しない。
    - `hidden`: True なら設定 / False なら削除。`None` 指定なら変更しない。
    - `genre`: 空文字なら削除、文字列なら設定。`None` 指定なら変更しない。
    """
    merged = dict(entry)
    if authors is not None:
        merged["authors"] = authors
    if tags is not None:
        merged["tags"] = tags
    if hidden is True:
        merged["hidden"] = True
    elif hidden is False:
        merged.pop("hidden", None)
    if genre is not None:
        if genre:
            merged["genre"] = genre
        else:
            merged.pop("genre", None)
    return merged


def has_meaningful_value(entry: dict) -> bool:
    """エントリに「空 list 以外」の意味のある値があるかを返す。

    `update_meta` で全フィールドに空 list が指定された場合にエントリ自体を消すかの判定に使う。
    """
    return any(not (isinstance(v, list) and not v) for v in entry.values())
