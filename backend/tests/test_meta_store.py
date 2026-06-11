"""
services.meta_store の純関数ユニットテスト（Phase 64: SQLite バックエンド対応版）。

`test_meta.py` は routers 経由の挙動を検証しているのに対し、
このファイルは `merge_entry_fields` / `has_meaningful_value` /
`update_meta_locked` を直接テストする。

テスト時は config.META_DB_DIR を tmp_path に向けることで meta.db を分離する。

実行方法:
    cd backend
    uv run pytest tests/test_meta_store.py -v
"""

import threading

import pytest

from services.meta_store import (
    has_meaningful_value,
    load_meta,
    merge_entry_fields,
    save_meta,
    update_meta_locked,
)

# ---------------------------------------------------------------------------
# フィクスチャ: DATA_DIR を tmp_path に向け、DB を毎テストで分離する
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path))
    yield


# ---------------------------------------------------------------------------
# merge_entry_fields
# ---------------------------------------------------------------------------


class TestMergeEntryFields:
    def test_authors_overwritten(self):
        result = merge_entry_fields({"authors": ["A"]}, authors=["B", "C"])
        assert result["authors"] == ["B", "C"]

    def test_none_authors_preserves_existing(self):
        result = merge_entry_fields({"authors": ["A"]}, authors=None, genre="G")
        assert result["authors"] == ["A"]
        assert result["genre"] == "G"

    def test_hidden_true_sets_field(self):
        result = merge_entry_fields({}, hidden=True)
        assert result["hidden"] is True

    def test_hidden_false_removes_field(self):
        result = merge_entry_fields({"hidden": True}, hidden=False)
        assert "hidden" not in result

    def test_hidden_false_with_no_existing_is_noop(self):
        result = merge_entry_fields({"authors": ["A"]}, hidden=False)
        assert "hidden" not in result
        assert result["authors"] == ["A"]

    def test_hidden_none_preserves_existing(self):
        result = merge_entry_fields({"hidden": True}, hidden=None, authors=["A"])
        assert result["hidden"] is True

    def test_genre_set(self):
        result = merge_entry_fields({}, genre="プリンセスコネクト")
        assert result["genre"] == "プリンセスコネクト"

    def test_genre_empty_string_removes_field(self):
        result = merge_entry_fields({"genre": "X"}, genre="")
        assert "genre" not in result

    def test_genre_none_preserves(self):
        result = merge_entry_fields({"genre": "X"}, genre=None)
        assert result["genre"] == "X"

    def test_view_count_preserved(self):
        """authors 等を更新しても view_count / last_viewed_at は保持される。"""
        result = merge_entry_fields(
            {"view_count": 5, "last_viewed_at": 1700000000.0, "authors": ["A"]},
            authors=["B"],
        )
        assert result["view_count"] == 5
        assert result["last_viewed_at"] == 1700000000.0
        assert result["authors"] == ["B"]

    def test_does_not_mutate_input(self):
        original = {"authors": ["A"]}
        merge_entry_fields(original, authors=["B"])
        assert original["authors"] == ["A"]

    def test_combined_update(self):
        result = merge_entry_fields(
            {"authors": ["old"], "view_count": 3},
            authors=["new"],
            hidden=True,
            genre="G",
        )
        assert result == {
            "authors": ["new"],
            "hidden": True,
            "genre": "G",
            "view_count": 3,
        }


# ---------------------------------------------------------------------------
# has_meaningful_value
# ---------------------------------------------------------------------------


class TestHasMeaningfulValue:
    def test_empty_dict_is_false(self):
        assert has_meaningful_value({}) is False

    def test_only_empty_lists_is_false(self):
        assert has_meaningful_value({"authors": []}) is False

    def test_view_count_makes_it_true(self):
        assert has_meaningful_value({"view_count": 1}) is True

    def test_hidden_true_makes_it_true(self):
        assert has_meaningful_value({"hidden": True}) is True

    def test_genre_makes_it_true(self):
        assert has_meaningful_value({"genre": "X"}) is True

    def test_non_empty_authors_makes_it_true(self):
        assert has_meaningful_value({"authors": ["A"]}) is True

    def test_mixed_empty_and_meaningful(self):
        assert has_meaningful_value({"authors": [], "view_count": 5}) is True


# ---------------------------------------------------------------------------
# update_meta_locked - 並行性
# ---------------------------------------------------------------------------


class TestUpdateMetaLocked:
    def test_basic_update(self):
        update_meta_locked("doujin", lambda d: d.update({"book.pdf": {"authors": ["A"]}}))

        meta = load_meta("doujin")
        assert meta == {"book.pdf": {"authors": ["A"]}}

    def test_concurrent_updates_no_lost_update(self):
        """10 スレッドで view_count を +1 ずつ → 最終値 10 になる（lost update が起きない）。"""
        update_meta_locked("doujin", lambda d: d.update({"book.pdf": {"view_count": 0}}))

        def _increment():
            def _apply(data):
                entry = data.setdefault("book.pdf", {})
                entry["view_count"] = entry.get("view_count", 0) + 1

            update_meta_locked("doujin", _apply)

        threads = [threading.Thread(target=_increment) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        meta = load_meta("doujin")
        assert meta["book.pdf"]["view_count"] == 10

    def test_independent_locks_per_source(self):
        """異なる source は独立して更新できる。"""
        update_meta_locked("doujin", lambda d: d.update({"a.pdf": {"authors": ["A"]}}))
        update_meta_locked("comic", lambda d: d.update({"b.pdf": {"authors": ["B"]}}))

        assert load_meta("doujin") == {"a.pdf": {"authors": ["A"]}}
        assert load_meta("comic") == {"b.pdf": {"authors": ["B"]}}


# ---------------------------------------------------------------------------
# load_meta / save_meta
# ---------------------------------------------------------------------------


class TestLoadSaveMeta:
    def test_load_missing_returns_empty_dict(self):
        assert load_meta("doujin") == {}

    def test_save_load_roundtrip(self):
        data = {"book.pdf": {"authors": ["A"], "view_count": 3}}
        save_meta("doujin", data)

        loaded = load_meta("doujin")
        assert loaded == data

    def test_save_preserves_non_ascii(self):
        data = {"本.pdf": {"authors": ["著者"], "genre": "オリジナル"}}
        save_meta("doujin", data)

        loaded = load_meta("doujin")
        assert loaded == data

    def test_save_optional_fields_roundtrip(self):
        """NotRequired フィールドが有り/無しどちらも正確に往復する。"""
        data = {
            "full.pdf": {
                "authors": ["作者"],
                "view_count": 5,
                "last_viewed_at": 1700000000.0,
                "hidden": True,
                "genre": "ジャンル",
                "read_state": "reading",
                "series_id": "sid",
                "series_title": "シリーズ",
                "series_index": 1.5,
                "volume": 2,
                "publisher": "出版社",
                "asin": "B000001",
                "isbn": "978-4000000000",
                "release_date": "2024-01-01",
            },
            "minimal.pdf": {"authors": []},
        }
        save_meta("novel", data)
        loaded = load_meta("novel")
        assert loaded == data
