"""
services.genre_store のユニットテスト（Phase 64: SQLite バックエンド対応版）。

ジャンルリストの永続化と books_meta からの初期生成を検証する。

実行方法:
    cd backend
    uv run pytest tests/test_genre_store.py -v
"""

import threading

import pytest

from services.genre_store import load_genres, save_genres
from services.meta_store import save_meta


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path))
    yield


def _seed_meta(source: str, data: dict) -> None:
    """books_meta にメタデータをシードする。"""
    save_meta(source, data)


# ---------------------------------------------------------------------------
# load_genres
# ---------------------------------------------------------------------------


class TestLoadGenres:
    def test_returns_saved_genres(self):
        save_genres("doujin", ["Voiceloid", "オリジナル"])
        assert load_genres("doujin") == ["Voiceloid", "オリジナル"]

    def test_creates_empty_when_no_meta(self):
        """books_meta に genre が無い場合は空 list を返す。"""
        genres = load_genres("doujin")
        assert genres == []

    def test_derives_from_meta_sorted_by_name(self):
        """books_meta の genre フィールドを名前順にソートした初期 list を返す（migration 用途）。"""
        _seed_meta(
            "doujin",
            {
                "a.pdf": {"authors": [], "genre": "ZZZ"},
                "b.pdf": {"authors": [], "genre": "AAA"},
                "c.pdf": {"authors": [], "genre": "MMM"},
            },
        )

        genres = load_genres("doujin")
        assert genres == ["AAA", "MMM", "ZZZ"]

    def test_dedupes_duplicate_genres_from_meta(self):
        """books_meta で同じ genre が複数書籍に付いていても 1 件にまとめる。"""
        _seed_meta(
            "doujin",
            {
                "a.pdf": {"authors": [], "genre": "X"},
                "b.pdf": {"authors": [], "genre": "X"},
                "c.pdf": {"authors": [], "genre": "Y"},
            },
        )

        assert load_genres("doujin") == ["X", "Y"]

    def test_genre_field_missing_returns_empty(self):
        _seed_meta("doujin", {"a.pdf": {"authors": ["X"]}})
        assert load_genres("doujin") == []

    def test_does_not_re_derive_after_save(self):
        """一度 save_genres した後は books_meta から再派生しない（保存済みを優先）。"""
        _seed_meta("doujin", {"a.pdf": {"authors": [], "genre": "FromMeta"}})
        save_genres("doujin", ["Explicit"])
        assert load_genres("doujin") == ["Explicit"]


# ---------------------------------------------------------------------------
# save_genres
# ---------------------------------------------------------------------------


class TestSaveGenres:
    def test_save_then_load_roundtrip(self):
        save_genres("doujin", ["A", "B", "C"])
        assert load_genres("doujin") == ["A", "B", "C"]

    def test_save_overwrites_previous(self):
        save_genres("doujin", ["A", "B"])
        save_genres("doujin", ["X"])
        assert load_genres("doujin") == ["X"]

    def test_save_preserves_non_ascii(self):
        save_genres("doujin", ["プリンセスコネクト", "Voiceloid"])
        assert load_genres("doujin") == ["プリンセスコネクト", "Voiceloid"]

    def test_independent_per_source(self):
        save_genres("doujin", ["A"])
        save_genres("comic", ["B"])

        assert load_genres("doujin") == ["A"]
        assert load_genres("comic") == ["B"]


# ---------------------------------------------------------------------------
# 並行性
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_save_no_corruption(self):
        """並行 save で DB が壊れない（最後の書き込みが残ればOK）。"""

        def _save(value):
            save_genres("doujin", [value])

        threads = [threading.Thread(target=_save, args=(f"V{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        loaded = load_genres("doujin")
        assert len(loaded) == 1
        assert loaded[0].startswith("V")
