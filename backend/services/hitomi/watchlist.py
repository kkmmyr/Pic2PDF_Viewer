"""hitomi.la 監視対象作者のリスト管理。

watchlist.json への CRUD と、表示名 → NOZOMI URL キーの正規化を提供する。
NOZOMI ファイル名そのものは `_` 区切り（hitomi.la 内部仕様）のため、
`urllib.parse.quote` で URL encode しつつ `_` は safe 文字として保持する。
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import date
from pathlib import Path
from typing import TypedDict

from . import nozomi


class WatchlistEntry(TypedDict):
    display_name: str
    normalized: str
    language: str
    added_at: str


class WatchlistError(Exception):
    """Watchlist 操作のエラー（重複登録・存在しない作者・不正な入力等）。"""


def normalize_artist_name(display_name: str) -> str:
    """表示名 → NOZOMI URL に埋め込むキーへ変換する。

    例:
      'AKA SHIO'  -> 'aka_shio'
      '山田 花子'  -> '%E5%B1%B1%E7%94%B0_%E8%8A%B1%E5%AD%90'
    """
    s = display_name.strip().lower().replace(" ", "_")
    return urllib.parse.quote(s, safe="_-")


def _watchlist_path(data_dir: Path) -> Path:
    return data_dir / "watchlist.json"


def load_watchlist(data_dir: Path) -> list[WatchlistEntry]:
    path = _watchlist_path(data_dir)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    artists = data.get("artists", [])
    if not isinstance(artists, list):
        return []
    return artists


def save_watchlist(data_dir: Path, entries: list[WatchlistEntry]) -> None:
    path = _watchlist_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"artists": entries}, f, ensure_ascii=False, indent=2)


def add_artist(
    data_dir: Path,
    display_name: str,
    language: str = "japanese",
    *,
    verify_existence: bool = True,
) -> WatchlistEntry:
    """監視対象を追加する。重複・空文字・hitomi.la 上の不在は WatchlistError で弾く。"""
    if not display_name.strip():
        raise WatchlistError("display_name is empty")

    normalized = normalize_artist_name(display_name)
    entries = load_watchlist(data_dir)

    for e in entries:
        if e["normalized"] == normalized and e["language"] == language:
            raise WatchlistError(f"already in watchlist: {normalized} ({language})")

    if verify_existence:
        try:
            exists = nozomi.check_nozomi_exists(normalized, language)
        except nozomi.HitomiError as ex:
            raise WatchlistError(f"verification failed: {ex}") from ex
        if not exists:
            raise WatchlistError(f"artist not found on hitomi.la: {normalized} ({language})")

    entry: WatchlistEntry = {
        "display_name": display_name.strip(),
        "normalized": normalized,
        "language": language,
        "added_at": date.today().isoformat(),
    }
    entries.append(entry)
    save_watchlist(data_dir, entries)
    return entry


def remove_artist(
    data_dir: Path,
    normalized: str,
    language: str = "japanese",
) -> bool:
    """監視対象を削除する。該当があれば True、なければ False を返す。"""
    entries = load_watchlist(data_dir)
    new_entries = [e for e in entries if not (e["normalized"] == normalized and e["language"] == language)]
    if len(new_entries) == len(entries):
        return False
    save_watchlist(data_dir, new_entries)
    return True
