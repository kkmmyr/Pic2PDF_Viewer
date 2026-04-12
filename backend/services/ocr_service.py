import subprocess
import os
import threading
from collections import deque
from typing import List, Optional, Dict, Any
from config import BATCH_OCR_LAUNCHER

class OCRService:
    _instance = None
    _class_lock = threading.Lock()

    def __new__(cls):
        with cls._class_lock:
            if cls._instance is None:
                instance = super(OCRService, cls).__new__(cls)
                instance.process = None
                instance.status = "idle"  # idle, running, error
                instance.logs = deque(maxlen=2000)
                instance.last_return_code = None
                instance._lock = threading.Lock()  # インスタンス状態を保護するロック
                cls._instance = instance
        return cls._instance

    @property
    def is_running(self) -> bool:
        # 注意: このプロパティは self._lock を保持した状態で呼び出すこと
        if self.status == "running":
            if self.process and self.process.poll() is None:
                return True
            else:
                # ゾンビプロセスのクリーンアップ
                self.status = "idle"
        return False

    def start_ocr(self, target_dir: Optional[str] = None) -> int:
        with self._lock:
            if self.is_running:
                raise RuntimeError("OCR process is already running")

            cmd = [BATCH_OCR_LAUNCHER]
            if target_dir:
                cmd.extend(["--target-dir", target_dir])

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    env=env
                )
                self.status = "running"
                self.last_return_code = None
                self.logs.clear()
                self.logs.append(f"Starting OCR process: {' '.join(cmd)}")
                pid = self.process.pid

            except Exception as e:
                self.status = "error"
                self.logs.append(f"Failed to start process: {str(e)}")
                raise e

        # スレッドはロック解放後に起動（デッドロック回避）
        t_log = threading.Thread(target=self._log_reader, daemon=True)
        t_log.start()

        t_monitor = threading.Thread(target=self._process_monitor, daemon=True)
        t_monitor.start()

        return pid

    def stop_ocr(self) -> None:
        with self._lock:
            if not self.is_running or not self.process:
                raise RuntimeError("No running process to stop")

            self.process.terminate()
            self.logs.append("Sent TERMINATE signal...")

        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            with self._lock:
                self.logs.append("Sent KILL signal...")

        with self._lock:
            self.status = "idle"

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": self.status,
                "last_return_code": self.last_return_code,
                "logs": list(self.logs)
            }

    def _log_reader(self):
        """プロセスの stdout を読み取ってログキューに追記する。"""
        if not self.process or not self.process.stdout:
            return

        for line in iter(self.process.stdout.readline, b''):
            decoded = line.decode('utf-8', errors='replace').rstrip()
            # deque.append は CPython の GIL により原子的なので lock 不要
            self.logs.append(decoded)
        self.process.stdout.close()

    def _process_monitor(self):
        """プロセス終了を監視してステータスを更新する。"""
        if not self.process:
            return

        self.process.wait()

        with self._lock:
            self.last_return_code = self.process.returncode
            self.status = "idle"

            if self.process.returncode == 0:
                self.logs.append("Process finished successfully.")
            else:
                self.logs.append(f"Process finished with error code: {self.process.returncode}")


# Global instance
ocr_service = OCRService()
