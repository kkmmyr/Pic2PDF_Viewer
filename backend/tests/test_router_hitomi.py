"""
routers.hitomi のユニットテスト。

services/hitomi/* の関数は別ファイルでカバー済みのため、ここは
HTTP 層のフロー（パラメータ伝達・例外マッピング・ロック）を中心に検証する。

実行方法:
    cd backend
    uv run pytest tests/test_router_hitomi.py -v
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def hitomi_data_dir(tmp_path, monkeypatch):
    """routers.hitomi.DATA_DIR を tmp_path に差し替える。"""
    data_dir = tmp_path / "hitomi"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("routers.hitomi.DATA_DIR", data_dir)
    return data_dir


def _seed_state(data_dir: Path, payload: dict) -> None:
    (data_dir / "state.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _seed_arrivals(data_dir: Path, items: list) -> None:
    (data_dir / "new_arrivals.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# GET /api/hitomi/new-arrivals
# ---------------------------------------------------------------------------


class TestNewArrivals:
    def test_returns_undismissed_sorted_newest_first(self, client, hitomi_data_dir):
        _seed_state(
            hitomi_data_dir,
            {
                "last_run_at": "2026-05-06T10:00:00",
                "last_run_status": "ok",
                "last_error": None,
            },
        )
        _seed_arrivals(
            hitomi_data_dir,
            [
                {"id": 1, "discovered_at": "2026-05-01T10:00:00", "dismissed": False, "title": "old"},
                {"id": 2, "discovered_at": "2026-05-05T10:00:00", "dismissed": False, "title": "new"},
                {"id": 3, "discovered_at": "2026-05-06T10:00:00", "dismissed": True, "title": "read"},
            ],
        )

        res = client.get("/api/hitomi/new-arrivals")
        assert res.status_code == 200
        body = res.json()
        # dismissed=true は除外、新着順
        assert [it["id"] for it in body["items"]] == [2, 1]
        assert body["unread_count"] == 2
        assert body["read_count"] == 1
        assert body["last_run_status"] == "ok"

    def test_returns_read_history_with_paging(self, client, hitomi_data_dir):
        _seed_arrivals(
            hitomi_data_dir,
            [
                {"id": 1, "discovered_at": "2026-05-01", "dismissed": True, "title": "old"},
                {"id": 2, "discovered_at": "2026-05-02", "dismissed": True, "title": "new"},
                {"id": 3, "discovered_at": "2026-05-03", "dismissed": False, "title": "unread"},
            ],
        )

        res = client.get("/api/hitomi/new-arrivals?status=read&offset=1&limit=1")
        body = res.json()
        assert [item["id"] for item in body["items"]] == [1]
        assert body["total"] == 2
        assert body["status"] == "read"

    def test_health_fields_default(self, client, hitomi_data_dir):
        """state.json なしでもヘルスフィールドはデフォルト値で返る。"""
        _seed_arrivals(hitomi_data_dir, [])
        res = client.get("/api/hitomi/new-arrivals")
        body = res.json()
        assert body["last_run_status"] == "never"


# ---------------------------------------------------------------------------
# POST /api/hitomi/dismiss/{id}
# ---------------------------------------------------------------------------


class TestDismiss:
    def test_dismisses_existing(self, client, hitomi_data_dir):
        _seed_arrivals(
            hitomi_data_dir,
            [
                {"id": 100, "discovered_at": "2026-05-06", "dismissed": False, "title": "x"},
            ],
        )
        res = client.post("/api/hitomi/dismiss/100")
        assert res.status_code == 200
        history = client.get("/api/hitomi/new-arrivals?status=read").json()
        assert history["items"][0]["id"] == 100
        assert history["items"][0]["read_at"] is not None

    def test_404_when_not_found(self, client, hitomi_data_dir):
        _seed_arrivals(hitomi_data_dir, [])
        res = client.post("/api/hitomi/dismiss/999")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/hitomi/dismiss-all
# ---------------------------------------------------------------------------


class TestDismissAll:
    def test_dismisses_all_undismissed(self, client, hitomi_data_dir):
        _seed_arrivals(
            hitomi_data_dir,
            [
                {"id": 1, "discovered_at": "2026-05-06", "dismissed": False, "title": "a"},
                {"id": 2, "discovered_at": "2026-05-06", "dismissed": False, "title": "b"},
                {"id": 3, "discovered_at": "2026-05-06", "dismissed": True, "title": "c"},
            ],
        )
        res = client.post("/api/hitomi/dismiss-all")
        assert res.status_code == 200
        # 既に dismissed=true だった分は count に含まれない
        assert res.json()["dismissed_count"] == 2


# ---------------------------------------------------------------------------
# GET /api/hitomi/watchlist
# ---------------------------------------------------------------------------


class TestGetWatchlist:
    def test_returns_artists(self, client, hitomi_data_dir):
        (hitomi_data_dir / "watchlist.json").write_text(
            json.dumps(
                {
                    "artists": [
                        {"normalized": "alice", "display_name": "Alice", "language": "japanese"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        res = client.get("/api/hitomi/watchlist")
        assert res.status_code == 200
        artists = res.json()["artists"]
        assert len(artists) == 1
        assert artists[0]["normalized"] == "alice"


# ---------------------------------------------------------------------------
# POST /api/hitomi/watchlist
# ---------------------------------------------------------------------------


class TestPostWatchlist:
    def test_added_when_artist_exists_on_hitomi(self, client, hitomi_data_dir, monkeypatch):
        # watchlist.add_artist 内部の実在確認（hitomi.la への実ネットワークアクセス）をモックし、
        # フレーキーテスト化（外部サイトの状態・可用性に依存）を防ぐ
        monkeypatch.setattr(
            "services.hitomi.watchlist.nozomi.check_nozomi_exists",
            lambda normalized, language: True,
        )
        # nozomi.fetch_nozomi_head を成功させる
        monkeypatch.setattr(
            "routers.hitomi.nozomi.fetch_nozomi_head",
            lambda normalized, language, count=1: [12345],
        )

        res = client.post("/api/hitomi/watchlist", json={"display_name": "Alice"})
        assert res.status_code == 200
        assert res.json()["normalized"]

        # state.json に top_id が初期化されていること
        with open(hitomi_data_dir / "state.json", encoding="utf-8") as f:
            state = json.load(f)
        assert any(v.get("top_id") == 12345 for v in state.get("artists", {}).values())

    def test_404_when_not_found_on_hitomi(self, client, hitomi_data_dir, monkeypatch):
        from services.hitomi.watchlist import WatchlistError

        def _add(*a, **kw):
            raise WatchlistError("Artist not found on hitomi.la")

        monkeypatch.setattr("routers.hitomi.watchlist.add_artist", _add)

        res = client.post("/api/hitomi/watchlist", json={"display_name": "ghost"})
        assert res.status_code == 404

    def test_400_when_duplicate(self, client, hitomi_data_dir, monkeypatch):
        from services.hitomi.watchlist import WatchlistError

        def _add(*a, **kw):
            raise WatchlistError("Already exists")

        monkeypatch.setattr("routers.hitomi.watchlist.add_artist", _add)

        res = client.post("/api/hitomi/watchlist", json={"display_name": "Alice"})
        assert res.status_code == 400

    def test_succeeds_even_if_top_id_init_fails(
        self,
        client,
        hitomi_data_dir,
        monkeypatch,
    ):
        """top_id 初期化（NOZOMI 取得）が失敗しても登録自体は成功する。"""
        from services.hitomi import nozomi

        def _fetch(*a, **kw):
            raise nozomi.HitomiError("network down")

        monkeypatch.setattr("routers.hitomi.nozomi.fetch_nozomi_head", _fetch)
        warning = Mock()
        monkeypatch.setattr("routers.hitomi.logger.warning", warning)

        res = client.post("/api/hitomi/watchlist", json={"display_name": "Alice"})
        assert res.status_code == 200
        warning.assert_called_once()
        assert "top_id 初期化スキップ" in warning.call_args.args[0]


# ---------------------------------------------------------------------------
# DELETE /api/hitomi/watchlist/{normalized}
# ---------------------------------------------------------------------------


class TestDeleteWatchlist:
    def test_removes_artist(self, client, hitomi_data_dir, monkeypatch):
        monkeypatch.setattr(
            "routers.hitomi.watchlist.remove_artist",
            lambda data_dir, normalized, language: True,
        )
        # state.json に該当エントリを置いておく
        _seed_state(hitomi_data_dir, {"artists": {"alice:japanese": {"top_id": 1}}})

        res = client.delete("/api/hitomi/watchlist/alice")
        assert res.status_code == 200

        # state.json から消えている
        with open(hitomi_data_dir / "state.json", encoding="utf-8") as f:
            state = json.load(f)
        assert "alice:japanese" not in state.get("artists", {})

    def test_404_when_not_found(self, client, hitomi_data_dir, monkeypatch):
        monkeypatch.setattr(
            "routers.hitomi.watchlist.remove_artist",
            lambda data_dir, normalized, language: False,
        )
        res = client.delete("/api/hitomi/watchlist/ghost")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/hitomi/run-now
# ---------------------------------------------------------------------------


class TestRunNow:
    def test_invokes_monitor_with_threshold_when_not_force(self, client, hitomi_data_dir, monkeypatch):
        captured = {}

        def _main(data_dir, threshold=None):
            captured["data_dir"] = data_dir
            captured["threshold"] = threshold
            return 0

        monkeypatch.setattr("routers.hitomi.hitomi_monitor.main", _main)
        _seed_state(hitomi_data_dir, {"last_run_at": "2026-05-06T01:00:00"})

        res = client.post("/api/hitomi/run-now")
        assert res.status_code == 200
        # threshold=None ではなく、当日 0:00 が渡される
        assert captured["threshold"] is not None

    def test_force_passes_none_threshold(self, client, hitomi_data_dir, monkeypatch):
        captured = {}

        def _main(data_dir, threshold=None):
            captured["threshold"] = threshold
            return 0

        monkeypatch.setattr("routers.hitomi.hitomi_monitor.main", _main)
        _seed_state(hitomi_data_dir, {})

        res = client.post("/api/hitomi/run-now?force=true")
        assert res.status_code == 200
        assert captured["threshold"] is None

    def test_returns_state_fields(self, client, hitomi_data_dir, monkeypatch):
        monkeypatch.setattr("routers.hitomi.hitomi_monitor.main", lambda data_dir, threshold=None: 0)
        _seed_state(
            hitomi_data_dir,
            {
                "last_run_at": "2026-05-06T10:00:00",
                "last_run_status": "ok",
                "last_error": None,
            },
        )

        res = client.post("/api/hitomi/run-now?force=true")
        body = res.json()
        assert body["exit_code"] == 0
        assert body["last_run_at"] == "2026-05-06T10:00:00"
        assert body["last_run_status"] == "ok"

    def test_409_when_already_running(self, client, hitomi_data_dir, monkeypatch):
        """_run_lock を強制的に取得した状態で再実行 → 409。"""
        from routers import hitomi as router_hitomi

        # ロックを別スレッドから永続的に保持させる
        acquired = router_hitomi._run_lock.acquire(blocking=False)
        try:
            res = client.post("/api/hitomi/run-now?force=true")
            assert res.status_code == 409
        finally:
            if acquired:
                router_hitomi._run_lock.release()

    def test_409_when_monitor_process_lock_is_held(self, client, hitomi_data_dir):
        from services.hitomi.process_lock import monitor_process_lock

        with monitor_process_lock(hitomi_data_dir):
            res = client.post("/api/hitomi/run-now?force=true")

        assert res.status_code == 409
        assert res.json()["detail"] == "監視が既に別プロセスで実行中です"
