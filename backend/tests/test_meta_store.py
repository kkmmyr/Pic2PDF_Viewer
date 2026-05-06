"""
services.meta_store の純関数ユニットテスト。

`test_meta.py` は routers 経由の挙動を検証しているのに対し、
このファイルは `merge_entry_fields` / `has_meaningful_value` /
`update_meta_locked` を直接テストする。

実行方法:
    cd backend
    uv run pytest tests/test_meta_store.py -v
"""
import sys
import os
import json
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.meta_store import (
    make_key,
    merge_entry_fields,
    has_meaningful_value,
    update_meta_locked,
    load_meta,
    save_meta,
)


# ---------------------------------------------------------------------------
# merge_entry_fields
# ---------------------------------------------------------------------------

class TestMergeEntryFields:
    def test_authors_overwritten(self):
        result = merge_entry_fields({"authors": ["A"]}, authors=["B", "C"])
        assert result["authors"] == ["B", "C"]

    def test_tags_overwritten(self):
        result = merge_entry_fields({"tags": ["x"]}, tags=["y"])
        assert result["tags"] == ["y"]

    def test_none_authors_preserves_existing(self):
        result = merge_entry_fields({"authors": ["A"]}, authors=None, tags=["t"])
        assert result["authors"] == ["A"]
        assert result["tags"] == ["t"]

    def test_none_tags_preserves_existing(self):
        result = merge_entry_fields({"tags": ["x"]}, tags=None, authors=["A"])
        assert result["tags"] == ["x"]

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
        result = merge_entry_fields({"hidden": True}, hidden=None, tags=["t"])
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
        """authors / tags 等を更新しても view_count / last_viewed_at は保持される。"""
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
            authors=["new"], tags=["t1"], hidden=True, genre="G",
        )
        assert result == {
            "authors": ["new"],
            "tags": ["t1"],
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
        assert has_meaningful_value({"authors": [], "tags": []}) is False

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
    def test_basic_update(self, tmp_path, monkeypatch):
        monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))

        update_meta_locked("generated", lambda d: d.update({"book.pdf": {"authors": ["A"]}}))

        meta = load_meta("generated")
        assert meta == {"book.pdf": {"authors": ["A"]}}

    def test_concurrent_updates_no_lost_update(self, tmp_path, monkeypatch):
        """10 スレッドで view_count を +1 ずつ → 最終値 10 になる（lost update が起きない）。"""
        monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))

        # 初期値
        update_meta_locked("generated", lambda d: d.update({"book.pdf": {"view_count": 0}}))

        def _increment():
            def _apply(data):
                entry = data.setdefault("book.pdf", {})
                entry["view_count"] = entry.get("view_count", 0) + 1
            update_meta_locked("generated", _apply)

        threads = [threading.Thread(target=_increment) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        meta = load_meta("generated")
        assert meta["book.pdf"]["view_count"] == 10

    def test_independent_locks_per_source(self, tmp_path, monkeypatch):
        """異なる source は独立して更新できる。"""
        monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))

        update_meta_locked("generated", lambda d: d.update({"a.pdf": {"authors": ["A"]}}))
        update_meta_locked("kindle", lambda d: d.update({"b.pdf": {"authors": ["B"]}}))

        assert load_meta("generated") == {"a.pdf": {"authors": ["A"]}}
        assert load_meta("kindle") == {"b.pdf": {"authors": ["B"]}}


# ---------------------------------------------------------------------------
# load_meta / save_meta
# ---------------------------------------------------------------------------

class TestLoadSaveMeta:
    def test_load_missing_returns_empty_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
        assert load_meta("generated") == {}

    def test_load_invalid_json_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
        meta_dir = tmp_path / "meta" / "generated"
        meta_dir.mkdir(parents=True)
        (meta_dir / "meta.json").write_text("{ broken json", encoding="utf-8")

        # 例外を投げず空 dict を返す
        assert load_meta("generated") == {}

    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
        data = {"book.pdf": {"authors": ["A"], "tags": ["t1"], "view_count": 3}}
        save_meta("generated", data)

        loaded = load_meta("generated")
        assert loaded == data

    def test_save_preserves_non_ascii(self, tmp_path, monkeypatch):
        monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
        data = {"本.pdf": {"authors": ["著者"], "genre": "オリジナル"}}
        save_meta("generated", data)

        # ファイル内容を直接確認（ensure_ascii=False で読める）
        path = tmp_path / "meta" / "generated" / "meta.json"
        text = path.read_text(encoding="utf-8")
        assert "著者" in text
