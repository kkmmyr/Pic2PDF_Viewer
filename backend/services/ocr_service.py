import threading
from collections import deque
from pathlib import Path
from typing import Any

from config import KINDLE_NOVEL_IMAGES_DIR, OCR_LOG_MAXLEN
from utils.logger import get_logger

logger = get_logger(__name__)


class OCRService:
    _instance = None
    _class_lock = threading.Lock()

    def __new__(cls):
        with cls._class_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._thread: threading.Thread | None = None
                instance.status = "idle"  # idle, running, error
                instance.logs: deque = deque(maxlen=OCR_LOG_MAXLEN)
                instance.last_return_code: int | None = None
                instance._lock = threading.Lock()
                cls._instance = instance
        return cls._instance

    @property
    def is_running(self) -> bool:
        # 注意: このプロパティは self._lock を保持した状態で呼び出すこと
        if self.status == "running":
            if self._thread and self._thread.is_alive():
                return True
            else:
                self.status = "idle"
        return False

    def start_ocr(self, target_dir: str | None = None) -> int:
        with self._lock:
            if self.is_running:
                raise RuntimeError("OCR process is already running")

            self.status = "running"
            self.last_return_code = None
            self.logs.clear()
            target_label = target_dir if target_dir else "all"
            self.logs.append(f"Starting OCR: target={target_label}")
            logger.info("Starting OCR thread: target=%s", target_label)

        def _body():
            try:
                self._run_ocr(target_dir)
            except Exception as e:
                self.logs.append(f"OCR error: {e}")
                logger.exception("OCR thread error")
                with self._lock:
                    self.status = "error"
                    self.last_return_code = 1

        self._thread = threading.Thread(target=_body, daemon=True)
        self._thread.start()
        return self._thread.ident or 0

    def stop_ocr(self) -> None:
        with self._lock:
            if not self.is_running:
                raise RuntimeError("No running OCR to stop")
            # スレッドは強制終了不可。ステータスをリセットして次の書籍完了後に停止
            self.status = "idle"
            self.logs.append("Stop requested (will finish current book).")
            logger.info("OCR stop requested")

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self.status,
                "last_return_code": self.last_return_code,
                "logs": list(self.logs),
            }

    def _run_ocr(self, target_dir: str | None) -> None:
        """OCR スレッド本体。run_ocr_subprocess + _store_ocr_pages を直接呼ぶ。"""
        from services.novel_db.builder import _store_ocr_pages
        from services.novel_db.extractor import run_ocr_subprocess

        images_base = Path(KINDLE_NOVEL_IMAGES_DIR)
        if target_dir:
            dirs = [images_base / target_dir]
        else:
            if not images_base.exists():
                raise FileNotFoundError(f"Images dir not found: {images_base}")
            dirs = sorted(d for d in images_base.iterdir() if d.is_dir())

        if not dirs:
            self.logs.append("No image directories found.")
            with self._lock:
                self.status = "idle"
                self.last_return_code = 0
            return

        total = len(dirs)
        self.logs.append(f"Found {total} book(s) to process.")

        for done, (book_name, pages) in enumerate(run_ocr_subprocess(dirs), start=1):
            self.logs.append(f"[{done}/{total}] {book_name}: {len(pages)} pages")
            _store_ocr_pages(book_name, pages)
            self.logs.append(f"[{done}/{total}] Stored: {book_name}")

        self.logs.append("OCR finished successfully.")
        logger.info("OCR finished successfully")
        with self._lock:
            self.status = "idle"
            self.last_return_code = 0


# Global instance
ocr_service = OCRService()
