"""tools.hitomi_monitor の判定と永続化境界を検証する。"""

import os
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools import hitomi_monitor
from tools.hitomi_monitor import should_skip_artist


class TestShouldSkipArtist:
    def _now(self):
        return datetime(2026, 4, 29, 12, 0, 0, tzinfo=UTC)

    def test_no_threshold_never_skips(self):
        # CLI 直接実行は threshold=None で常に通常処理
        assert should_skip_artist("2026-04-29T11:00:00+00:00", None) is False

    def test_no_checked_at_never_skips(self):
        # 初回監視（前回 checked_at なし）→ スキップしない
        threshold = self._now() - timedelta(hours=72)
        assert should_skip_artist(None, threshold) is False
        assert should_skip_artist("", threshold) is False

    def test_recent_check_within_threshold_skips(self):
        # 1 時間前にチェック済み → 72 時間以内 → スキップ
        threshold = self._now() - timedelta(hours=72)
        recent = (self._now() - timedelta(hours=1)).isoformat()
        assert should_skip_artist(recent, threshold) is True

    def test_old_check_beyond_threshold_does_not_skip(self):
        # 100 時間前にチェック済み → 72 時間より古い → スキップしない
        threshold = self._now() - timedelta(hours=72)
        old = (self._now() - timedelta(hours=100)).isoformat()
        assert should_skip_artist(old, threshold) is False

    def test_invalid_iso_does_not_skip(self):
        # 不正な日付文字列は安全側に倒して False（通常実行）
        threshold = self._now() - timedelta(hours=72)
        assert should_skip_artist("not-a-date", threshold) is False

    def test_naive_datetime_treated_as_utc(self):
        # tz 情報なしの datetime は UTC として扱う
        threshold = self._now() - timedelta(hours=72)
        recent_naive = (self._now() - timedelta(hours=1)).replace(tzinfo=None).isoformat()
        # naive を UTC とみなして比較 → threshold より新しいのでスキップ
        assert should_skip_artist(recent_naive, threshold) is True

    def test_exactly_at_threshold_does_not_skip(self):
        # checked_at == threshold (ぴったり) は「より新しい」ではないのでスキップしない
        threshold = self._now() - timedelta(hours=72)
        assert should_skip_artist(threshold.isoformat(), threshold) is False


def test_main_reuses_one_http_client(monkeypatch, tmp_path):
    state = {"artists": {}}
    entry = {"normalized": "author", "display_name": "Author", "language": "japanese"}
    client = MagicMock(name="shared_client")
    client_context = MagicMock()
    client_context.__enter__.return_value = client
    client_context.__exit__.return_value = False
    client_factory = MagicMock(return_value=client_context)
    fetch_nozomi = MagicMock(return_value=[123])
    fetch_metadata = MagicMock(return_value={"title": "book", "files": []})

    monkeypatch.setattr(hitomi_monitor.httpx, "Client", client_factory)
    monkeypatch.setattr(hitomi_monitor.state_store, "load_state", lambda _path: state)
    monkeypatch.setattr(hitomi_monitor.watchlist, "load_watchlist", lambda _path: [entry])
    monkeypatch.setattr(hitomi_monitor.arrival_store, "import_legacy_json", lambda _path: 0)
    monkeypatch.setattr(hitomi_monitor.nozomi, "fetch_nozomi_head", fetch_nozomi)
    monkeypatch.setattr(hitomi_monitor.metadata, "fetch_metadata", fetch_metadata)
    monkeypatch.setattr(hitomi_monitor.arrival_store, "merge_new_items", lambda _items: 1)
    monkeypatch.setattr(hitomi_monitor.state_store, "save_state", lambda _path, _state: None)
    monkeypatch.setattr(hitomi_monitor.notify, "notify_run_result", lambda **_kwargs: None)

    assert hitomi_monitor.main(tmp_path) == 0
    client_factory.assert_called_once_with(timeout=hitomi_monitor.nozomi.DEFAULT_TIMEOUT)
    fetch_nozomi.assert_called_once_with("author", "japanese", count=20, client=client)
    fetch_metadata.assert_called_once_with(123, client=client)
    client_context.__exit__.assert_called_once()


def test_main_keeps_failed_metadata_id_for_next_run(monkeypatch, tmp_path):
    state = {"artists": {"author:japanese": {"top_id": 100}}}
    entry = {"normalized": "author", "display_name": "Author", "language": "japanese"}
    saved_states = []
    merged_items = []

    monkeypatch.setattr(hitomi_monitor.watchlist, "load_watchlist", lambda _path: [entry])
    monkeypatch.setattr(hitomi_monitor.state_store, "load_state", lambda _path: state)
    monkeypatch.setattr(hitomi_monitor.state_store, "save_state", lambda _path, value: saved_states.append(value))
    monkeypatch.setattr(hitomi_monitor.arrival_store, "import_legacy_json", lambda _path: 0)
    monkeypatch.setattr(hitomi_monitor.nozomi, "fetch_nozomi_head", lambda *args, **kwargs: [102, 101, 100])

    def _fetch_metadata(gallery_id, *, client):
        if gallery_id == 101:
            raise hitomi_monitor.metadata.HitomiMetadataError("temporary failure")
        return {"title": f"book-{gallery_id}", "files": []}

    monkeypatch.setattr(hitomi_monitor.metadata, "fetch_metadata", _fetch_metadata)

    def _merge(items):
        merged_items.extend(items)
        return len(items)

    monkeypatch.setattr(hitomi_monitor.arrival_store, "merge_new_items", _merge)
    monkeypatch.setattr(hitomi_monitor.notify, "notify_run_result", lambda **_kwargs: None)

    assert hitomi_monitor.main(tmp_path) == 1
    assert [item["id"] for item in merged_items] == [102]
    artist_state = saved_states[-1]["artists"]["author:japanese"]
    assert artist_state["top_id"] == 102
    assert artist_state["pending_gallery_ids"] == [101]


def test_main_retries_pending_id_after_top_id_advanced(monkeypatch, tmp_path):
    state = {
        "artists": {
            "author:japanese": {
                "top_id": 102,
                "pending_gallery_ids": [101],
            }
        }
    }
    entry = {"normalized": "author", "display_name": "Author", "language": "japanese"}
    saved_states = []
    merged_items = []

    monkeypatch.setattr(hitomi_monitor.watchlist, "load_watchlist", lambda _path: [entry])
    monkeypatch.setattr(hitomi_monitor.state_store, "load_state", lambda _path: state)
    monkeypatch.setattr(hitomi_monitor.state_store, "save_state", lambda _path, value: saved_states.append(value))
    monkeypatch.setattr(hitomi_monitor.arrival_store, "import_legacy_json", lambda _path: 0)
    monkeypatch.setattr(hitomi_monitor.nozomi, "fetch_nozomi_head", lambda *args, **kwargs: [102, 101, 100])
    monkeypatch.setattr(
        hitomi_monitor.metadata,
        "fetch_metadata",
        lambda gallery_id, *, client: {"title": f"book-{gallery_id}", "files": []},
    )

    def _merge(items):
        merged_items.extend(items)
        return len(items)

    monkeypatch.setattr(hitomi_monitor.arrival_store, "merge_new_items", _merge)
    monkeypatch.setattr(hitomi_monitor.notify, "notify_run_result", lambda **_kwargs: None)

    assert hitomi_monitor.main(tmp_path) == 0
    assert [item["id"] for item in merged_items] == [101]
    assert saved_states[-1]["artists"]["author:japanese"]["pending_gallery_ids"] == []


def test_main_does_not_advance_state_when_arrival_merge_fails(monkeypatch, tmp_path):
    initial_state = {
        "artists": {
            "author:japanese": {
                "top_id": 100,
                "pending_gallery_ids": [99],
            }
        }
    }
    entry = {"normalized": "author", "display_name": "Author", "language": "japanese"}
    hitomi_monitor.state_store.save_state(tmp_path, initial_state)

    monkeypatch.setattr(hitomi_monitor.watchlist, "load_watchlist", lambda _path: [entry])
    monkeypatch.setattr(hitomi_monitor.arrival_store, "import_legacy_json", lambda _path: 0)
    monkeypatch.setattr(hitomi_monitor.nozomi, "fetch_nozomi_head", lambda *args, **kwargs: [102, 101, 100])
    monkeypatch.setattr(
        hitomi_monitor.metadata,
        "fetch_metadata",
        lambda gallery_id, *, client: {"title": f"book-{gallery_id}", "files": []},
    )

    def _fail_merge(_items):
        raise OSError("database unavailable")

    monkeypatch.setattr(hitomi_monitor.arrival_store, "merge_new_items", _fail_merge)

    assert hitomi_monitor.main(tmp_path) == 2
    persisted = hitomi_monitor.state_store.load_state(tmp_path)
    assert persisted["artists"] == initial_state["artists"]
