"""
services.ocr_service のユニットテスト。

OCRService は singleton（`__new__` キャッシュ）なので、テスト間で
`_instance = None` にリセットしてから使う。`subprocess.Popen` はモック化。

実行方法:
    cd backend
    uv run pytest tests/test_ocr_service.py -v
"""
import sys
import os
import time
import threading
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import services.ocr_service as ocr_module
from services.ocr_service import OCRService


@pytest.fixture(autouse=True)
def _reset_singleton():
    """各テスト前後で OCRService の singleton をリセットする。"""
    OCRService._instance = None
    yield
    OCRService._instance = None


def _make_fake_popen(returncode: int = 0, stdout_lines: list[bytes] | None = None,
                     auto_exit: bool = True):
    """subprocess.Popen をモック化するファクトリ。

    Args:
        auto_exit: True なら wait() 即時 returncode 返却（自然終了テスト用）。
                   False なら exit_event がセットされるまで wait() がブロックする
                   （stop_ocr / 二重起動など、プロセス生存中のテスト用）。
    """
    if stdout_lines is None:
        stdout_lines = []

    proc = MagicMock()
    proc.pid = 12345
    proc.returncode = returncode
    poll_state = {"alive": True}
    proc.poll = lambda: None if poll_state["alive"] else returncode

    # stdout.readline は順に bytes を返し、最後に b'' で終端
    iter_obj = iter(stdout_lines + [b""])
    proc.stdout = MagicMock()
    proc.stdout.readline = lambda: next(iter_obj, b"")

    exit_event = threading.Event()
    if auto_exit:
        exit_event.set()

    def _wait(timeout=None):
        if not exit_event.wait(timeout=timeout):
            import subprocess as _sp
            raise _sp.TimeoutExpired(cmd="x", timeout=timeout)
        poll_state["alive"] = False
        return returncode

    proc.wait = _wait
    proc.terminate = lambda: exit_event.set()  # terminate されたら exit
    proc.kill = lambda: exit_event.set()
    proc._exit_event = exit_event  # テスト側から制御するため

    return proc


# ---------------------------------------------------------------------------
# start_ocr
# ---------------------------------------------------------------------------

class TestStartOcr:
    def test_starts_process_and_returns_pid(self, monkeypatch):
        proc = _make_fake_popen(returncode=0, stdout_lines=[b"hello\n"], auto_exit=False)
        captured = {}

        def _fake_popen(cmd, **kw):
            captured["cmd"] = cmd
            captured["env"] = kw.get("env", {})
            return proc

        monkeypatch.setattr(ocr_module.subprocess, "Popen", _fake_popen)

        svc = OCRService()
        pid = svc.start_ocr()

        assert pid == 12345
        assert svc.status == "running"
        # PYTHONIOENCODING が設定されている
        assert captured["env"].get("PYTHONIOENCODING") == "utf-8"

    def test_target_dir_passed_as_argument(self, monkeypatch):
        proc = _make_fake_popen(auto_exit=False)
        captured = {}

        def _fake_popen(cmd, **kw):
            captured["cmd"] = cmd
            return proc

        monkeypatch.setattr(ocr_module.subprocess, "Popen", _fake_popen)

        svc = OCRService()
        svc.start_ocr(target_dir="D:/some/path")

        assert "--target-dir" in captured["cmd"]
        idx = captured["cmd"].index("--target-dir")
        assert captured["cmd"][idx + 1] == "D:/some/path"

    def test_double_start_raises(self, monkeypatch):
        proc = _make_fake_popen(auto_exit=False)
        monkeypatch.setattr(ocr_module.subprocess, "Popen", lambda *a, **kw: proc)

        svc = OCRService()
        svc.start_ocr()

        with pytest.raises(RuntimeError) as exc:
            svc.start_ocr()
        assert "already running" in str(exc.value)

    def test_popen_failure_sets_error_status(self, monkeypatch):
        def _fake_popen(*a, **kw):
            raise OSError("popen failed")

        monkeypatch.setattr(ocr_module.subprocess, "Popen", _fake_popen)

        svc = OCRService()
        with pytest.raises(OSError):
            svc.start_ocr()
        assert svc.status == "error"
        assert any("Failed to start" in log for log in svc.logs)


# ---------------------------------------------------------------------------
# stop_ocr
# ---------------------------------------------------------------------------

class TestStopOcr:
    def test_terminate_called_when_running(self, monkeypatch):
        proc = _make_fake_popen(auto_exit=False)
        terminate_called = {"count": 0}
        original_terminate = proc.terminate

        def _track_terminate():
            terminate_called["count"] += 1
            original_terminate()

        proc.terminate = _track_terminate
        monkeypatch.setattr(ocr_module.subprocess, "Popen", lambda *a, **kw: proc)

        svc = OCRService()
        svc.start_ocr()
        svc.stop_ocr()

        assert terminate_called["count"] == 1

    def test_kill_when_terminate_times_out(self, monkeypatch):
        """terminate が effect を持たず timeout になったら kill が呼ばれる。"""
        proc = _make_fake_popen(auto_exit=False)
        # terminate を no-op にして wait を timeout させる
        proc.terminate = lambda: None
        kill_event = threading.Event()
        original_kill = proc.kill

        def _track_kill():
            kill_event.set()
            original_kill()

        proc.kill = _track_kill
        monkeypatch.setattr(ocr_module.subprocess, "Popen", lambda *a, **kw: proc)

        # PROCESS_TERMINATE_TIMEOUT_SEC を短縮してテスト高速化
        monkeypatch.setattr(ocr_module, "PROCESS_TERMINATE_TIMEOUT_SEC", 0.1)

        svc = OCRService()
        svc.start_ocr()
        svc.stop_ocr()

        assert kill_event.is_set()

    def test_stop_when_not_running_raises(self):
        svc = OCRService()
        # idle 状態
        with pytest.raises(RuntimeError) as exc:
            svc.stop_ocr()
        assert "No running process" in str(exc.value)


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

    def test_returns_logs_as_list(self, monkeypatch):
        svc = OCRService()
        svc.logs.extend(["line1", "line2"])
        status = svc.get_status()
        assert status["logs"] == ["line1", "line2"]
        # logs は list 形式で返る（deque ではない）
        assert isinstance(status["logs"], list)


# ---------------------------------------------------------------------------
# _process_monitor — プロセス完了後の状態更新
# ---------------------------------------------------------------------------

class TestProcessMonitor:
    def test_status_returns_to_idle_on_completion(self, monkeypatch):
        proc = _make_fake_popen(returncode=0, stdout_lines=[b"done\n"])
        monkeypatch.setattr(ocr_module.subprocess, "Popen", lambda *a, **kw: proc)

        svc = OCRService()
        svc.start_ocr()

        # _process_monitor は別スレッドで wait を呼ぶ
        for _ in range(50):
            if svc.status == "idle":
                break
            time.sleep(0.05)

        assert svc.status == "idle"
        assert svc.last_return_code == 0

    def test_failure_records_nonzero_return_code(self, monkeypatch):
        proc = _make_fake_popen(returncode=1, stdout_lines=[b"err\n"])
        monkeypatch.setattr(ocr_module.subprocess, "Popen", lambda *a, **kw: proc)

        svc = OCRService()
        svc.start_ocr()
        for _ in range(50):
            if svc.status == "idle":
                break
            time.sleep(0.05)

        assert svc.last_return_code == 1
        assert any("error code: 1" in log for log in svc.logs)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_returns_same_instance(self):
        a = OCRService()
        b = OCRService()
        assert a is b
