"""
routers.ocr のユニットテスト。

OCRService 自体は test_ocr_service.py で検証済みなので、
ここは HTTP 層のフロー（status code・例外マッピング）に絞る。

実行方法:
    cd backend
    uv run pytest tests/test_router_ocr.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(autouse=True)
def _stub_ocr_service(monkeypatch):
    """ocr_service グローバルインスタンスを差し替えるためのスタブ。"""
    class _Stub:
        def __init__(self):
            self.start_calls = []
            self.stop_calls = 0
            self.status_payload = {"status": "idle", "last_return_code": None, "logs": []}
            self.start_should_raise = None
            self.stop_should_raise = None
            self.start_return = 999

        def start_ocr(self, target_dir=None):
            self.start_calls.append(target_dir)
            if self.start_should_raise:
                raise self.start_should_raise
            return self.start_return

        def stop_ocr(self):
            self.stop_calls += 1
            if self.stop_should_raise:
                raise self.stop_should_raise

        def get_status(self):
            return self.status_payload

    stub = _Stub()
    monkeypatch.setattr("routers.ocr.ocr_service", stub)
    return stub


# ---------------------------------------------------------------------------
# POST /api/ocr/run
# ---------------------------------------------------------------------------

class TestRunOcr:
    def test_starts_and_returns_pid(self, client, _stub_ocr_service):
        _stub_ocr_service.start_return = 42
        res = client.post("/api/ocr/run")
        assert res.status_code == 200
        assert res.json() == {"status": "started", "pid": 42}

    def test_target_dir_query_passed_through(self, client, _stub_ocr_service):
        client.post("/api/ocr/run?target_dir=D:/some/dir")
        assert _stub_ocr_service.start_calls == ["D:/some/dir"]

    def test_runtime_error_returns_400(self, client, _stub_ocr_service):
        _stub_ocr_service.start_should_raise = RuntimeError("already running")
        res = client.post("/api/ocr/run")
        assert res.status_code == 400
        assert "already running" in res.json()["detail"]

    def test_unexpected_error_returns_500(self, client, _stub_ocr_service):
        _stub_ocr_service.start_should_raise = OSError("popen failed")
        res = client.post("/api/ocr/run")
        assert res.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/ocr/stop
# ---------------------------------------------------------------------------

class TestStopOcr:
    def test_stops_when_running(self, client, _stub_ocr_service):
        res = client.post("/api/ocr/stop")
        assert res.status_code == 200
        assert res.json() == {"status": "stopped"}
        assert _stub_ocr_service.stop_calls == 1

    def test_runtime_error_returns_400(self, client, _stub_ocr_service):
        _stub_ocr_service.stop_should_raise = RuntimeError("No running process")
        res = client.post("/api/ocr/stop")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/ocr/status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_returns_payload(self, client, _stub_ocr_service):
        _stub_ocr_service.status_payload = {
            "status": "running",
            "last_return_code": None,
            "logs": ["line1", "line2"],
        }
        res = client.get("/api/ocr/status")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "running"
        assert body["logs"] == ["line1", "line2"]
