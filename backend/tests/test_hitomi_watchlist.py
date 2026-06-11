"""services.hitomi.watchlist のユニットテスト。

normalize_artist_name は純粋関数。CRUD は tmp_path で隔離。
NOZOMI 存在確認は monkeypatch で無効化（ネットワーク非依存）。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.hitomi import watchlist
from services.hitomi.watchlist import (
    WatchlistError,
    add_artist,
    load_watchlist,
    normalize_artist_name,
    remove_artist,
    save_watchlist,
)


class TestNormalizeArtistName:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("aka_shio", "aka_shio"),
            ("AKA SHIO", "aka_shio"),
            ("AKA_SHIO", "aka_shio"),
            ("aka shio", "aka_shio"),
            ("  aka shio  ", "aka_shio"),  # 前後空白除去
            ("Some Artist Name", "some_artist_name"),
            ("artist-name", "artist-name"),  # ハイフンは保持
        ],
    )
    def test_ascii_normalization(self, name, expected):
        assert normalize_artist_name(name) == expected

    def test_japanese_is_url_encoded(self):
        # 山田 花子 → 山田_花子 → URL encode
        result = normalize_artist_name("山田 花子")
        # %xx シーケンスを含む（具体値は実装依存だが、underscore は残る）
        assert "%" in result
        assert "_" in result

    def test_underscore_preserved_via_safe(self):
        # safe='_-' のため _ は encode されない
        assert normalize_artist_name("a_b") == "a_b"
        assert normalize_artist_name("a-b") == "a-b"


class TestWatchlistCrud:
    def test_load_empty_when_no_file(self, tmp_path):
        assert load_watchlist(tmp_path) == []

    def test_save_then_load_roundtrip(self, tmp_path):
        entries = [
            {
                "display_name": "aka shio",
                "normalized": "aka_shio",
                "language": "japanese",
                "added_at": "2026-04-29",
            },
        ]
        save_watchlist(tmp_path, entries)
        assert load_watchlist(tmp_path) == entries

    def test_save_creates_data_dir(self, tmp_path):
        target = tmp_path / "subdir" / "hitomi"
        save_watchlist(target, [])
        assert (target / "watchlist.json").exists()

    def test_add_artist_writes_entry(self, tmp_path, monkeypatch):
        monkeypatch.setattr(watchlist.nozomi, "check_nozomi_exists", lambda *a, **k: True)
        entry = add_artist(tmp_path, "AKA SHIO", "japanese")
        assert entry["normalized"] == "aka_shio"
        assert entry["display_name"] == "AKA SHIO"
        assert entry["language"] == "japanese"

        loaded = load_watchlist(tmp_path)
        assert len(loaded) == 1
        assert loaded[0]["normalized"] == "aka_shio"

    def test_add_artist_rejects_duplicate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(watchlist.nozomi, "check_nozomi_exists", lambda *a, **k: True)
        add_artist(tmp_path, "aka_shio", "japanese")
        with pytest.raises(WatchlistError, match="already in watchlist"):
            add_artist(tmp_path, "AKA SHIO", "japanese")  # 大文字違いでも normalized 同じ

    def test_add_artist_rejects_empty(self, tmp_path):
        with pytest.raises(WatchlistError, match="empty"):
            add_artist(tmp_path, "   ", "japanese", verify_existence=False)

    def test_add_artist_rejects_when_nozomi_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(watchlist.nozomi, "check_nozomi_exists", lambda *a, **k: False)
        with pytest.raises(WatchlistError, match="not found on hitomi.la"):
            add_artist(tmp_path, "nonexistent", "japanese")

    def test_add_artist_skip_verification(self, tmp_path):
        # verify_existence=False ならネットワーク不要
        entry = add_artist(tmp_path, "test", "japanese", verify_existence=False)
        assert entry["normalized"] == "test"

    def test_remove_artist_returns_true_on_hit(self, tmp_path):
        save_watchlist(
            tmp_path,
            [
                {"display_name": "a", "normalized": "a", "language": "japanese", "added_at": "2026-04-29"},
                {"display_name": "b", "normalized": "b", "language": "japanese", "added_at": "2026-04-29"},
            ],
        )
        assert remove_artist(tmp_path, "a", "japanese") is True
        assert [e["normalized"] for e in load_watchlist(tmp_path)] == ["b"]

    def test_remove_artist_returns_false_when_missing(self, tmp_path):
        save_watchlist(tmp_path, [])
        assert remove_artist(tmp_path, "nonexistent", "japanese") is False

    def test_language_distinguishes_entries(self, tmp_path):
        save_watchlist(
            tmp_path,
            [
                {"display_name": "a", "normalized": "a", "language": "japanese", "added_at": "2026-04-29"},
                {"display_name": "a", "normalized": "a", "language": "english", "added_at": "2026-04-29"},
            ],
        )
        # japanese を消しても english は残る
        assert remove_artist(tmp_path, "a", "japanese") is True
        loaded = load_watchlist(tmp_path)
        assert len(loaded) == 1
        assert loaded[0]["language"] == "english"

    def test_persists_as_utf8_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(watchlist.nozomi, "check_nozomi_exists", lambda *a, **k: True)
        add_artist(tmp_path, "山田", "japanese")
        text = (tmp_path / "watchlist.json").read_text(encoding="utf-8")
        # ensure_ascii=False で日本語がそのまま保存される
        assert "山田" in text
        # 念のため再 parse
        data = json.loads(text)
        assert data["artists"][0]["display_name"] == "山田"
