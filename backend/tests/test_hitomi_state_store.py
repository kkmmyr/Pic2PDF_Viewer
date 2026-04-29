"""services.hitomi.state_store のユニットテスト。

ファイル I/O は tmp_path で隔離。時刻は明示注入で再現性を確保。
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.hitomi.state_store import (
    dismiss,
    dismiss_all,
    load_arrivals,
    load_state,
    merge_new_items,
    purge_expired,
    save_arrivals,
    save_state,
)


class TestStateLoadSave:
    def test_load_returns_default_when_no_file(self, tmp_path):
        state = load_state(tmp_path)
        assert state["last_run_status"] == "never"
        assert state["last_run_at"] is None
        assert state["artists"] == {}

    def test_save_then_load_roundtrip(self, tmp_path):
        save_state(tmp_path, {
            "last_run_at": "2026-04-29T03:00:00+09:00",
            "last_run_status": "ok",
            "last_error": None,
            "artists": {"aka_shio:japanese": {"top_id": 100, "checked_at": "x"}},
        })
        loaded = load_state(tmp_path)
        assert loaded["last_run_status"] == "ok"
        assert loaded["artists"]["aka_shio:japanese"]["top_id"] == 100


class TestMergeNewItems:
    def test_adds_to_empty(self, tmp_path):
        added = merge_new_items(tmp_path, [
            {"id": 1, "title": "a", "discovered_at": "2026-04-29T03:00:00+09:00", "dismissed": False},
            {"id": 2, "title": "b", "discovered_at": "2026-04-29T03:00:00+09:00", "dismissed": False},
        ])
        assert added == 2
        assert len(load_arrivals(tmp_path)["items"]) == 2

    def test_ignores_duplicate_ids(self, tmp_path):
        save_arrivals(tmp_path, {"items": [{"id": 1, "dismissed": False}]})
        added = merge_new_items(tmp_path, [
            {"id": 1, "dismissed": False},  # 既存
            {"id": 2, "dismissed": False},  # 新規
        ])
        assert added == 1
        ids = [it["id"] for it in load_arrivals(tmp_path)["items"]]
        assert sorted(ids) == [1, 2]

    def test_dedups_within_batch(self, tmp_path):
        added = merge_new_items(tmp_path, [
            {"id": 1, "dismissed": False},
            {"id": 1, "dismissed": False},  # 同バッチ内重複
            {"id": 2, "dismissed": False},
        ])
        assert added == 2

    def test_empty_input_no_write(self, tmp_path):
        assert merge_new_items(tmp_path, []) == 0
        # 空入力時はファイル作成も発生しない
        assert not (tmp_path / "new_arrivals.json").exists()


class TestDismiss:
    def test_dismiss_marks_item(self, tmp_path):
        save_arrivals(tmp_path, {"items": [
            {"id": 1, "dismissed": False},
            {"id": 2, "dismissed": False},
        ]})
        assert dismiss(tmp_path, 1) is True
        items = load_arrivals(tmp_path)["items"]
        by_id = {it["id"]: it for it in items}
        assert by_id[1]["dismissed"] is True
        assert by_id[2]["dismissed"] is False

    def test_dismiss_returns_false_when_missing(self, tmp_path):
        save_arrivals(tmp_path, {"items": [{"id": 1, "dismissed": False}]})
        assert dismiss(tmp_path, 999) is False

    def test_dismiss_already_dismissed_is_false(self, tmp_path):
        # 既読済みのものを再 dismiss しても変更なし
        save_arrivals(tmp_path, {"items": [{"id": 1, "dismissed": True}]})
        assert dismiss(tmp_path, 1) is False

    def test_dismiss_all_marks_unread_only(self, tmp_path):
        save_arrivals(tmp_path, {"items": [
            {"id": 1, "dismissed": False},
            {"id": 2, "dismissed": True},  # 既読
            {"id": 3, "dismissed": False},
        ]})
        assert dismiss_all(tmp_path) == 2  # 2件のみ


class TestPurgeExpired:
    def _now(self):
        return datetime(2026, 4, 29, 0, 0, 0, tzinfo=timezone.utc)

    def test_purges_dismissed_older_than_threshold(self, tmp_path):
        old = (self._now() - timedelta(days=31)).isoformat()
        recent = (self._now() - timedelta(days=10)).isoformat()
        save_arrivals(tmp_path, {"items": [
            {"id": 1, "dismissed": True, "discovered_at": old},     # purge 対象
            {"id": 2, "dismissed": True, "discovered_at": recent},  # 30日以内なので残す
            {"id": 3, "dismissed": False, "discovered_at": old},    # 未既読なので残す
        ]})
        removed = purge_expired(tmp_path, threshold_days=30, now=self._now())
        assert removed == 1
        ids = sorted(it["id"] for it in load_arrivals(tmp_path)["items"])
        assert ids == [2, 3]

    def test_keeps_when_no_discovered_at(self, tmp_path):
        save_arrivals(tmp_path, {"items": [
            {"id": 1, "dismissed": True},  # discovered_at 欠損
        ]})
        removed = purge_expired(tmp_path, threshold_days=30, now=self._now())
        assert removed == 0
        assert len(load_arrivals(tmp_path)["items"]) == 1

    def test_keeps_when_invalid_iso(self, tmp_path):
        save_arrivals(tmp_path, {"items": [
            {"id": 1, "dismissed": True, "discovered_at": "not-iso-format"},
        ]})
        removed = purge_expired(tmp_path, threshold_days=30, now=self._now())
        assert removed == 0

    def test_no_changes_no_write(self, tmp_path):
        save_arrivals(tmp_path, {"items": [
            {"id": 1, "dismissed": False, "discovered_at": (self._now() - timedelta(days=1)).isoformat()},
        ]})
        # ファイル mtime を記録
        path = tmp_path / "new_arrivals.json"
        mtime_before = path.stat().st_mtime
        purge_expired(tmp_path, threshold_days=30, now=self._now())
        # 削除対象ゼロ → 書き込み発生しない（mtime 変化しない）
        assert path.stat().st_mtime == mtime_before
