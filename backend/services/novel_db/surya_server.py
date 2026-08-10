"""Surya llama-server process lifecycle。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


class SuryaServer:
    """既存llama-serverへ接続するか、worker lifetimeで所有する。"""

    def __init__(
        self,
        base_url: str,
        *,
        executable: str | None = None,
        model_path: str | None = None,
        mmproj_path: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.executable = executable
        self.model_path = model_path
        self.mmproj_path = mmproj_path
        self._process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> SuryaServer:
        if self._healthy():
            return self
        self._start_owned_server()
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise RuntimeError(f"llama-server exited with code {self._process.returncode}")
            if self._healthy():
                return self
            time.sleep(1)
        self.close()
        raise TimeoutError("llama-server did not become ready within 120 seconds")

    @property
    def owns_process(self) -> bool:
        return self._process is not None

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def close(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        self._process = None

    def _healthy(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/models",
                timeout=2,
            ) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def _start_owned_server(self) -> None:
        paths = [self.executable, self.model_path, self.mmproj_path]
        if not all(paths):
            raise RuntimeError(
                "Surya server is unavailable. Set SURYA_LLAMA_SERVER_PATH, "
                "SURYA_MODEL_PATH, and SURYA_MMPROJ_PATH for automatic startup."
            )
        assert self.executable and self.model_path and self.mmproj_path
        for path in paths:
            if not Path(str(path)).is_file():
                raise FileNotFoundError(f"Surya runtime file not found: {path}")

        parsed = urlparse(self.base_url)
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("automatic llama-server startup requires a localhost SURYA_INFERENCE_URL")
        port = parsed.port or 8768
        cmd = [
            self.executable,
            "--model",
            self.model_path,
            "--mmproj",
            self.mmproj_path,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--ctx-size",
            "16384",
            "--parallel",
            "1",
            "--gpu-layers",
            "99",
            "--image-min-tokens",
            "1024",
            "--jinja",
        ]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._process = subprocess.Popen(
            cmd,
            stdout=sys.stderr,
            stderr=sys.stderr,
            creationflags=creationflags,
        )
