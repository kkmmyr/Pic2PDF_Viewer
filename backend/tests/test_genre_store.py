"""
services.genre_store のユニットテスト。

ジャンルリストの永続化と meta.json からの初期生成を検証する。

実行方法:
    cd backend
    uv run pytest tests/test_genre_store.py -v
"""
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def store_env(tmp_path, monkeypatch):
    """genre_store と meta_store のデータディレクトリを tmp_path 配下に設定する。"""
    monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("services.genre_store.DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "services.genre_store.GENRE_STORE_DIR",
        str(tmp_path / "genres"),
    )
    return tmp_path


def _seed_meta(tmp_path, source: str, data: dict) -> None:
    meta_dir = tmp_path / "meta" / source
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "meta.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# load_genres
# ---------------------------------------------------------------------------

class TestLoadGenres:
    def test_returns_existing_file(self, store_env):
        from services.genre_store import load_genres
        genres_dir = store_env / "genres"
        genres_dir.mkdir(parents=True, exist_ok=True)
        (genres_dir / "doujin.json").write_text(
            json.dumps(["Voiceloid", "オリジナル"]), encoding="utf-8"
        )

        assert load_genres("doujin") == ["Voiceloid", "オリジナル"]

    def test_creates_empty_when_no_meta(self, store_env):
        """meta.json が無い場合は空 list を作成して保存する。"""
        from services.genre_store import load_genres
        genres = load_genres("doujin")
        assert genres == []
        # ファイルが作成されている
        assert (store_env / "genres" / "doujin.json").exists()

    def test_derives_from_meta_sorted_by_name(self, store_env):
        """meta.json の genre フィールドを名前順にソートした初期 list を返す（migration 用途）。"""
        _seed_meta(store_env, "doujin", {
            "a.pdf": {"genre": "ZZZ"},
            "b.pdf": {"genre": "AAA"},
            "c.pdf": {"genre": "MMM"},
        })

        from services.genre_store import load_genres
        genres = load_genres("doujin")
        # 単純にソート（並び順は UI 側で reorder されるため、初期値は予測可能であればよい）
        assert genres == ["AAA", "MMM", "ZZZ"]

    def test_dedupes_duplicate_genres_from_meta(self, store_env):
        """meta.json で同じ genre が複数書籍に付いていても 1 件にまとめる。"""
        _seed_meta(store_env, "doujin", {
            "a.pdf": {"genre": "X"},
            "b.pdf": {"genre": "X"},
            "c.pdf": {"genre": "Y"},
        })

        from services.genre_store import load_genres
        assert load_genres("doujin") == ["X", "Y"]

    def test_genre_field_missing_returns_empty(self, store_env):
        _seed_meta(store_env, "doujin", {"a.pdf": {"authors": ["X"]}})

        from services.genre_store import load_genres
        assert load_genres("doujin") == []


# ---------------------------------------------------------------------------
# save_genres
# ---------------------------------------------------------------------------

class TestSaveGenres:
    def test_save_then_load_roundtrip(self, store_env):
        from services.genre_store import load_genres, save_genres
        save_genres("doujin", ["A", "B", "C"])
        assert load_genres("doujin") == ["A", "B", "C"]

    def test_save_creates_directory(self, store_env):
        """genres/ ディレクトリが存在しなくても自動作成される。"""
        from services.genre_store import save_genres
        save_genres("doujin", ["X"])
        assert (store_env / "genres" / "doujin.json").exists()

    def test_save_preserves_non_ascii(self, store_env):
        from services.genre_store import save_genres
        save_genres("doujin", ["プリンセスコネクト", "Voiceloid"])

        content = (store_env / "genres" / "doujin.json").read_text(encoding="utf-8")
        assert "プリンセスコネクト" in content

    def test_independent_per_source(self, store_env):
        from services.genre_store import load_genres, save_genres
        save_genres("doujin", ["A"])
        save_genres("comic", ["B"])

        assert load_genres("doujin") == ["A"]
        assert load_genres("comic") == ["B"]


# ---------------------------------------------------------------------------
# 並行性
# ---------------------------------------------------------------------------

class TestConcurrency:
    def test_concurrent_save_no_corruption(self, store_env):
        """並行 save でファイルが壊れない（最後の書き込みが残ればOK）。"""
        from services.genre_store import load_genres, save_genres

        def _save(value):
            save_genres("doujin", [value])

        threads = [threading.Thread(target=_save, args=(f"V{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 必ず読める（破壊されていない）
        loaded = load_genres("doujin")
        assert len(loaded) == 1
        assert loaded[0].startswith("V")
