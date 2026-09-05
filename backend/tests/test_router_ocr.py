"""routers.ocr のユニットテスト（job_queue ベース実装）。

実行方法:
    cd backend
    uv run pytest tests/test_router_ocr.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.novel_db.migrations import upgrade_head


@pytest.fixture
def novel_db(tmp_data_dir):
    """novel.db スキーマを初期化する（rebuild_jobs テーブルが必要なテスト用）。"""
    upgrade_head()
    return tmp_data_dir


# ---------------------------------------------------------------------------
# POST /api/ocr/run
# ---------------------------------------------------------------------------


class TestRunOcr:
    def test_enqueues_all_and_returns_queued(self, client, monkeypatch):
        monkeypatch.setattr(
            "routers.ocr.job_queue.enqueue",
            lambda job_type, target_id=None, mode="rebuild": (1, 1),
        )
        res = client.post("/api/ocr/run")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "queued"
        assert body["job_id"] == 1
        assert body["queue_position"] == 1

    def test_target_dir_creates_book_job(self, client, monkeypatch):
        calls: list = []

        def _enqueue(job_type, target_id=None, mode="rebuild"):
            calls.append((job_type, target_id, mode))
            return (2, 1)

        monkeypatch.setattr("routers.ocr.job_queue.enqueue", _enqueue)
        client.post("/api/ocr/run?target_dir=mybook")
        assert calls == [("book", "mybook", "ocr")]

    @pytest.mark.parametrize("target_dir", ["../outside", "C:/Windows", "folder/book"])
    def test_rejects_unsafe_target_dir(self, client, monkeypatch, target_dir):
        monkeypatch.setattr(
            "routers.ocr.job_queue.enqueue",
            lambda *args, **kwargs: pytest.fail("unsafe target must not be enqueued"),
        )

        res = client.post("/api/ocr/run", params={"target_dir": target_dir})
        assert res.status_code == 400

    def test_no_target_dir_creates_all_job(self, client, monkeypatch):
        calls: list = []

        def _enqueue(job_type, target_id=None, mode="rebuild"):
            calls.append((job_type, target_id, mode))
            return (3, 1)

        monkeypatch.setattr("routers.ocr.job_queue.enqueue", _enqueue)
        client.post("/api/ocr/run")
        assert calls == [("all", None, "ocr")]


# ---------------------------------------------------------------------------
# POST /api/ocr/stop
# ---------------------------------------------------------------------------


class TestStopOcr:
    def test_cancels_queued_jobs(self, client, monkeypatch):
        monkeypatch.setattr("routers.ocr.job_queue.cancel_queued_by_mode", lambda m: [10, 11])
        res = client.post("/api/ocr/stop")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "canceled"
        assert body["canceled_jobs"] == [10, 11]

    def test_returns_400_when_nothing_queued(self, client, monkeypatch):
        monkeypatch.setattr("routers.ocr.job_queue.cancel_queued_by_mode", lambda m: [])
        res = client.post("/api/ocr/stop")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/ocr/status
# ---------------------------------------------------------------------------


class TestGetOcrStatus:
    def test_idle_when_no_jobs(self, client, novel_db):
        res = client.get("/api/ocr/status")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "idle"
        assert body["logs"] == []
        assert body["last_return_code"] is None

    def test_running_when_job_active(self, client, novel_db):
        from services.novel_db.connection import with_db

        with with_db() as conn:
            conn.execute(
                "INSERT INTO rebuild_jobs "
                "(job_type, mode, state, current_step, current_detail, "
                " progress_total, progress_done) "
                "VALUES ('all', 'ocr', 'running', 'OCR中', 'book1を処理中', 5, 2)"
            )
            conn.commit()

        res = client.get("/api/ocr/status")
        body = res.json()
        assert body["status"] == "running"
        assert any("2" in log for log in body["logs"])
        assert "OCR中" in body["logs"]
        assert body["last_return_code"] is None

    def test_running_when_jobs_queued(self, client, novel_db):
        from services.novel_db.connection import with_db

        with with_db() as conn:
            conn.execute("INSERT INTO rebuild_jobs (job_type, mode, state) VALUES ('all', 'ocr', 'queued')")
            conn.execute("INSERT INTO rebuild_jobs (job_type, mode, state) VALUES ('book', 'ocr', 'queued')")
            conn.commit()

        res = client.get("/api/ocr/status")
        body = res.json()
        assert body["status"] == "running"
        assert any("2" in log for log in body["logs"])


class TestOcrAgentApi:
    @pytest.mark.parametrize("page_manifest", [{}, {"runtime_manifest": None}])
    def test_page_submit_rejects_missing_manifest(self, client, monkeypatch, page_manifest):
        import config

        monkeypatch.setattr(config.app_settings, "OCR_AGENT_ENABLED", True)
        monkeypatch.setattr(config, "KINDLE_CAPTURE_AGENT_TOKEN", "test-token")
        captured = []
        monkeypatch.setattr("routers.ocr.ocr_agent_jobs.submit_page", lambda *args: captured.append(args))
        response = client.post(
            "/api/ocr/agents/jobs/7/pages",
            headers={"X-Capture-Agent-Token": "test-token"},
            json={
                "agent_id": "windows-1",
                "book_name": "book",
                "page": {
                    "page_no": 1,
                    "image_sha256": "a" * 64,
                    "state": "passed",
                    "full_text": "本文",
                    "char_count": 2,
                    "raw_output": "",
                    "block_count": 1,
                    "quality_flags": [],
                    "ink_coverage": 1.0,
                    "attempt_count": 1,
                    **page_manifest,
                },
            },
        )
        assert response.status_code == 422
        assert any(error["loc"] == ["body", "page", "runtime_manifest"] for error in response.json()["detail"])
        assert not captured

    def test_claim_requires_enabled_agent_and_valid_token(self, client, monkeypatch):
        import config

        monkeypatch.setattr(config.app_settings, "OCR_AGENT_ENABLED", True)
        monkeypatch.setattr(config, "KINDLE_CAPTURE_AGENT_TOKEN", "test-token")
        monkeypatch.setattr("routers.ocr.ocr_agent_jobs.claim", lambda agent_id: None)

        unauthorized = client.post(
            "/api/ocr/agents/claim",
            json={"agent_id": "windows-1"},
            headers={"X-Capture-Agent-Token": "wrong"},
        )
        assert unauthorized.status_code == 401

        response = client.post(
            "/api/ocr/agents/claim",
            json={"agent_id": "windows-1"},
            headers={"X-Capture-Agent-Token": "test-token"},
        )
        assert response.status_code == 200
        assert response.json() == {"job": None}

    def test_page_submit_forwards_validated_payload(self, client, monkeypatch):
        import config

        monkeypatch.setattr(config.app_settings, "OCR_AGENT_ENABLED", True)
        monkeypatch.setattr(config, "KINDLE_CAPTURE_AGENT_TOKEN", "test-token")
        captured: list[tuple] = []

        def submit(job_id, agent_id, book_name, page):
            captured.append((job_id, agent_id, book_name, page))
            return {
                "job_id": job_id,
                "status": "passed",
                "book_name": book_name,
                "page_no": page["page_no"],
            }

        monkeypatch.setattr("routers.ocr.ocr_agent_jobs.submit_page", submit)
        response = client.post(
            "/api/ocr/agents/jobs/7/pages",
            headers={"X-Capture-Agent-Token": "test-token"},
            json={
                "agent_id": "windows-1",
                "book_name": "book",
                "page": {
                    "runtime_manifest": {"schema_version": 1, "engine": "surya2", "model_revision": "test-model"},
                    "page_no": 1,
                    "image_sha256": "a" * 64,
                    "state": "passed",
                    "full_text": "本文",
                    "char_count": 2,
                    "raw_output": "",
                    "block_count": 1,
                    "quality_flags": [],
                    "ink_coverage": 1.0,
                    "attempt_count": 1,
                },
            },
        )
        assert response.status_code == 200
        assert captured[0][0:3] == (7, "windows-1", "book")

    def test_idle_after_completed_job(self, client, novel_db):
        from services.novel_db.connection import with_db

        with with_db() as conn:
            conn.execute(
                "INSERT INTO rebuild_jobs (job_type, mode, state, finished_at) "
                "VALUES ('all', 'ocr', 'completed', datetime('now'))"
            )
            conn.commit()

        res = client.get("/api/ocr/status")
        body = res.json()
        assert body["status"] == "idle"
        assert body["last_return_code"] == 0

    def test_error_after_failed_job(self, client, novel_db):
        from services.novel_db.connection import with_db

        with with_db() as conn:
            conn.execute(
                "INSERT INTO rebuild_jobs "
                "(job_type, mode, state, finished_at, error_message) "
                "VALUES ('all', 'ocr', 'failed', datetime('now'), 'OCR subprocess error')"
            )
            conn.commit()

        res = client.get("/api/ocr/status")
        body = res.json()
        assert body["status"] == "error"
        assert body["last_return_code"] == 1
        assert "OCR subprocess error" in body["logs"]

    def test_running_job_takes_priority_over_completed(self, client, novel_db):
        from services.novel_db.connection import with_db

        with with_db() as conn:
            conn.execute(
                "INSERT INTO rebuild_jobs (job_type, mode, state, finished_at) "
                "VALUES ('all', 'ocr', 'completed', datetime('now'))"
            )
            conn.execute(
                "INSERT INTO rebuild_jobs "
                "(job_type, mode, state, current_step) "
                "VALUES ('all', 'ocr', 'running', 'OCR実行中')"
            )
            conn.commit()

        res = client.get("/api/ocr/status")
        body = res.json()
        assert body["status"] == "running"
