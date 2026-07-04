"""
routers.generate のユニットテスト。

PDF 生成ジョブ起動・進捗取得を検証する。
`scan_and_generate` は重い処理なのでモック化してジョブのライフサイクルだけ追う。

実行方法:
    cd backend
    uv run pytest tests/test_router_generate.py -v
"""

import asyncio
import time

from services.doujin_watcher import PendingItem, doujin_watcher
from services.meta_store import load_meta, save_meta
from services.pdf_generator import GenerateResult

# ---------------------------------------------------------------------------
# POST /api/generate
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_missing_input_dir_returns_503(self, client, tmp_data_dir, monkeypatch):
        import config

        monkeypatch.setattr(config, "DOUJIN_INPUT_DIR", "/nope/does/not/exist/qwerty")
        res = client.post("/api/generate")
        assert res.status_code == 503

    def test_returns_job_id_and_pending(self, client, tmp_data_dir, monkeypatch):
        # scan_and_generate を即終了するモックに差し替え
        monkeypatch.setattr(
            "services.generate_service.scan_and_generate",
            lambda *a, **kw: GenerateResult(generated=[], failed_items=[]),
        )

        res = client.post("/api/generate")
        assert res.status_code == 200
        body = res.json()
        assert "job_id" in body
        assert body["status"] == "pending"

    def test_initial_genre_written_to_meta(self, client, tmp_data_dir, monkeypatch):
        """新規生成された PDF に genre: "オリジナル" が初期書き込みされる。"""
        monkeypatch.setattr(
            "services.generate_service.scan_and_generate",
            lambda *a, **kw: GenerateResult(generated=["new1.pdf", "new2.pdf"], failed_items=[]),
        )

        res = client.post("/api/generate")
        job_id = res.json()["job_id"]

        # ジョブ完了を待つ
        for _ in range(50):
            r = client.get(f"/api/generate/job/{job_id}")
            if r.json()["status"] == "completed":
                break
            time.sleep(0.05)
        assert r.json()["status"] == "completed"

        meta = load_meta("doujin")
        assert meta["new1.pdf"]["genre"] == "オリジナル"
        assert meta["new2.pdf"]["genre"] == "オリジナル"

    def test_existing_meta_genre_preserved(self, client, tmp_data_dir, monkeypatch):
        """既存メタデータがある書籍には genre を上書きしない。"""
        save_meta("doujin", {"existing.pdf": {"genre": "プリンセスコネクト", "authors": ["A"]}})

        monkeypatch.setattr(
            "services.generate_service.scan_and_generate",
            lambda *a, **kw: GenerateResult(generated=["existing.pdf"], failed_items=[]),
        )

        res = client.post("/api/generate")
        job_id = res.json()["job_id"]
        for _ in range(50):
            if client.get(f"/api/generate/job/{job_id}").json()["status"] == "completed":
                break
            time.sleep(0.05)

        meta = load_meta("doujin")
        assert meta["existing.pdf"]["genre"] == "プリンセスコネクト"
        assert meta["existing.pdf"]["authors"] == ["A"]

    def test_failed_job_records_error(self, client, tmp_data_dir, monkeypatch):
        def _boom(*a, **kw):
            raise RuntimeError("boom!")

        monkeypatch.setattr("services.generate_service.scan_and_generate", _boom)

        res = client.post("/api/generate")
        job_id = res.json()["job_id"]
        for _ in range(50):
            r = client.get(f"/api/generate/job/{job_id}").json()
            if r["status"] == "failed":
                break
            time.sleep(0.05)
        assert r["status"] == "failed"
        assert "boom" in r["error"]

    def test_failed_items_message(self, client, tmp_data_dir, monkeypatch):
        monkeypatch.setattr(
            "services.generate_service.scan_and_generate",
            lambda *a, **kw: GenerateResult(
                generated=["ok.pdf"],
                failed_items=[("bad.zip", "Corrupt zip")],
            ),
        )

        res = client.post("/api/generate")
        job_id = res.json()["job_id"]
        for _ in range(50):
            r = client.get(f"/api/generate/job/{job_id}").json()
            if r["status"] == "completed":
                break
            time.sleep(0.05)
        assert "1 succeeded" in r["message"]
        assert "1 failed" in r["message"]

    def test_busy_returns_409_with_active_job_id(self, client, tmp_data_dir):
        """生成ロック取得中の手動起動は409 + 実行中job_idを返す。

        conftest の TestClient はコンテキストマネージャなしで使うため、リクエスト毎に
        イベントループが破棄され、create_task したジョブがレスポンス返却時にキャンセル
        → finally でロック解放、となり実ジョブで「実行中」状態を維持できない。
        ここではロックとアクティブジョブ ID を直接セットして実行中を再現する。
        """
        from services import generate_service

        asyncio.run(generate_service.generate_lock.acquire())
        generate_service._active_job_id = "busy-job-123"
        try:
            res = client.post("/api/generate")
            assert res.status_code == 409
            assert "busy-job-123" in res.json()["detail"]
        finally:
            generate_service._active_job_id = None
            generate_service.generate_lock.release()

    def test_success_clears_watcher_last_attempted(self, client, tmp_data_dir, monkeypatch):
        """手動実行成功 = 再試行の意思表示。自動監視の last_attempted ブロックを解除する。"""
        monkeypatch.setattr(
            "services.generate_service.scan_and_generate",
            lambda *a, **kw: GenerateResult(generated=[], failed_items=[]),
        )
        doujin_watcher._last_attempted = frozenset({("stale", "zip", 1, 1.0)})

        res = client.post("/api/generate")
        assert res.status_code == 200

        assert doujin_watcher._last_attempted is None


# ---------------------------------------------------------------------------
# GET /api/generate/job/{job_id}
# ---------------------------------------------------------------------------


class TestGetGenerateJob:
    def test_404_for_unknown_job(self, client, tmp_data_dir):
        res = client.get("/api/generate/job/nonexistent-uuid")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/generate/watcher
# ---------------------------------------------------------------------------


class TestGenerateWatcher:
    def test_default_shape(self, client, tmp_data_dir):
        res = client.get("/api/generate/watcher")
        assert res.status_code == 200
        body = res.json()
        assert set(body.keys()) == {
            "enabled",
            "state",
            "interval_sec",
            "last_scan_at",
            "pending_items",
            "active_job_id",
            "last_auto_job",
            "retry_blocked",
        }
        assert isinstance(body["enabled"], bool)
        assert isinstance(body["interval_sec"], int)
        assert isinstance(body["pending_items"], list)

    def test_reflects_current_watcher_state(self, client, tmp_data_dir, monkeypatch):
        monkeypatch.setattr(doujin_watcher, "state", "waiting_stable")
        monkeypatch.setattr(doujin_watcher, "pending_items", [PendingItem(name="foo.zip", kind="zip")])
        monkeypatch.setattr(doujin_watcher, "retry_blocked", True)

        res = client.get("/api/generate/watcher")
        body = res.json()
        assert body["state"] == "waiting_stable"
        assert body["pending_items"] == [{"name": "foo.zip", "kind": "zip"}]
        assert body["retry_blocked"] is True
