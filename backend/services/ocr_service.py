import subprocess
import os
import threading
from collections import deque
from typing import List, Optional, Dict, Any
from config import BATCH_OCR_LAUNCHER

class OCRService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OCRService, cls).__new__(cls)
            cls._instance.process = None
            cls._instance.status = "idle" # idle, running, error
            cls._instance.logs = deque(maxlen=2000)
            cls._instance.last_return_code = None
        return cls._instance

    @property
    def is_running(self) -> bool:
        if self.status == "running":
            if self.process and self.process.poll() is None:
                return True
            else:
                # Zombie cleanup if any
                self.status = "idle"
        return False

    def start_ocr(self, target_dir: Optional[str] = None) -> int:
        if self.is_running:
            raise RuntimeError("OCR process is already running")

        # Prepare command - use batch launcher which sets up PYTHONPATH
        cmd = [BATCH_OCR_LAUNCHER]
        
        # If we want to support arguments later, we can add them to cmd.
        if target_dir:
            cmd.extend(["--target-dir", target_dir])

        # Force UTF-8 output
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Merge stderr to stdout
                bufsize=1, # Line buffered
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                env=env
            )
            self.status = "running"
            self.last_return_code = None
            self.logs.clear()
            self.logs.append(f"Starting OCR process: {' '.join(cmd)}")

            # Start Log Reader Thread
            t = threading.Thread(target=self._log_reader, daemon=True)
            t.start()
            
            # Start Monitor Thread
            t_monitor = threading.Thread(target=self._process_monitor, daemon=True)
            t_monitor.start()

            return self.process.pid
        except Exception as e:
            self.status = "error"
            self.logs.append(f"Failed to start process: {str(e)}")
            raise e

    def stop_ocr(self) -> None:
        if not self.is_running or not self.process:
            raise RuntimeError("No running process to stop")
        
        self.process.terminate()
        self.logs.append("Sent TERMINATE signal...")
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.logs.append("Sent KILL signal...")
        
        self.status = "idle"

    def get_status(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "last_return_code": self.last_return_code,
            "logs": list(self.logs)
        }

    def _log_reader(self):
        """Reads stdout lines from process and appends to log queue."""
        if not self.process or not self.process.stdout:
            return

        for line in iter(self.process.stdout.readline, b''):
            decoded = line.decode('utf-8', errors='replace').rstrip()
            self.logs.append(decoded)
        self.process.stdout.close()

    def _process_monitor(self):
        if not self.process:
            return
            
        self.process.wait()
        self.last_return_code = self.process.returncode
        self.status = "idle"
        
        if self.process.returncode == 0:
            self.logs.append("Process finished successfully.")
        else:
            self.logs.append(f"Process finished with error code: {self.process.returncode}")

# Global instance
ocr_service = OCRService()
