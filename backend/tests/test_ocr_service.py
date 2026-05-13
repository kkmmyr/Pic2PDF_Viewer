"""
services.ocr_service のユニットテスト（スレッドベース実装）。

OCRService は singleton なのでテスト間で `_instance = None` にリセットする。
_run_ocr をインスタンス属性で差し替えてスレッドを制御する。

実行方法:
    cd backend
    uv run pytest tests/test_ocr_service.py -v
"""
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.ocr_service import OCRService


@pytest.fixture(autouse=True)
def _reset_singleton():
    """各テスト前後で OCRService の singleton をリセットする。"""
    OCRService._instance = None
    yield
    OCRService._instance = None


def _patch_blocking(svc: OCRService) -> threading.Event:
    """_run_ocr をブロッキングモックに差し替え、unblock イベントを返す。"""
    event = threading.Event()

    def _blocked(target_dir=None):
        event.wait(timeout=5.0)
        with svc._lock:
            svc.status = "idle"
            svc.last_return_code = 0

    svc._run_ocr = _blocked
    return event


def _patch_instant(svc: OCRService) -> None:
    """_run_ocr を即時完了モックに差し替える。"""
    def _noop(target_dir=None):
        with svc._lock:
            svc.status = "idle"
            svc.last_return_code = 0

    svc._run_ocr = _noop


def _wait_until(condition, timeout=2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------------------
# start_ocr
# ---------------------------------------------------------------------------

class TestStartOcr:
    def test_returns_int_and_sets_running(self):
        svc = OCRService()
        unblock = _patch_blocking(svc)

        tid = svc.start_ocr()
        assert isinstance(tid, int)
        assert svc.status == "running"
        unblock.set()

    def test_target_dir_passed_to_run_ocr(self):
        svc = OCRService()
        received: dict = {}

        def _capture(target_dir=None):
            received["target_dir"] = target_dir
            with svc._lock:
                svc.status = "idle"
                svc.last_return_code = 0

        svc._run_ocr = _capture
        svc.start_ocr(target_dir="mybook")

        assert _wait_until(lambda: "target_dir" in received)
        assert received["target_dir"] == "mybook"

    def test_double_start_raises(self):
        svc = OCRService()
        unblock = _patch_blocking(svc)

        svc.start_ocr()
        with pytest.raises(RuntimeError) as exc:
            svc.start_ocr()
        assert "already running" in str(exc.value)
        unblock.set()

    def test_failure_sets_error_status(self):
        svc = OCRService()

        def _failing(target_dir=None):
            raise RuntimeError("OCR failed")

        svc._run_ocr = _failing
        svc.start_ocr()

        assert _wait_until(lambda: svc.status != "running")
        assert svc.status == "error"
        assert svc.last_return_code == 1
        assert any("OCR error" in log for log in svc.logs)

    def test_logs_contain_start_message(self):
        svc = OCRService()
        unblock = _patch_blocking(svc)

        svc.start_ocr()
        assert any("Starting OCR" in log for log in svc.logs)
        unblock.set()

    def test_status_returns_to_idle_on_completion(self):
        svc = OCRService()
        _patch_instant(svc)

        svc.start_ocr()
        assert _wait_until(lambda: svc.status == "idle")
        assert svc.last_return_code == 0


# ---------------------------------------------------------------------------
# stop_ocr
# ---------------------------------------------------------------------------

class TestStopOcr:
    def test_stop_sets_status_idle(self):
        svc = OCRService()
        unblock = _patch_blocking(svc)

        svc.start_ocr()
        assert svc.status == "running"
        svc.stop_ocr()
        assert svc.status == "idle"
        unblock.set()

    def test_stop_when_not_running_raises(self):
        svc = OCRService()
        with pytest.raises(RuntimeError) as exc:
            svc.stop_ocr()
        assert "No running OCR" in str(exc.value)

    def test_stop_appends_log(self):
        svc = OCRService()
        unblock = _patch_blocking(svc)

        svc.start_ocr()
        svc.stop_ocr()
        assert any("Stop requested" in log for log in svc.logs)
        unblock.set()


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_idle_status(self):
        svc = OCRService()
        status = svc.get_status()
        assert status["status"] == "idle"
        assert status["last_return_code"] is None
        assert status["logs"] == []

    def test_returns_logs_as_list(self):
        svc = OCRService()
        svc.logs.extend(["line1", "line2"])
        status = svc.get_status()
        assert status["logs"] == ["line1", "line2"]
        assert isinstance(status["logs"], list)

    def test_running_status_while_thread_alive(self):
        svc = OCRService()
        unblock = _patch_blocking(svc)

        svc.start_ocr()
        assert svc.get_status()["status"] == "running"
        unblock.set()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_returns_same_instance(self):
        a = OCRService()
        b = OCRService()
        assert a is b
