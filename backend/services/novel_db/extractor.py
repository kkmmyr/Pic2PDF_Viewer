"""ページ単位テキスト抽出。

- PDF モード: PyMuPDF で縦書きブロックを連結（既存書籍との後方互換用）
- 画像モード: ocr_worker.py を common/ocr/venv の Python でサブプロセス実行（§5.1.1）

詳細は docs/design/詳細設計/機能別/小説RAG_パイプライン設計.md §2。
"""

from __future__ import annotations

import json
import os
import platform
import queue
import re
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NotRequired, TypedDict

import fitz

from .ocr_worker_protocol import OcrProgressPayload as OcrProgressEvent
from .ocr_worker_protocol import OcrWorkerTask as OcrTask

_NEWLINE_RE = re.compile(r"\n+")


def _resolve_ocr_python() -> str:
    """OCR venv の Python 実行ファイルパスを解決する。

    優先順位: app_settings.OCR_PYTHON → プラットフォーム既定値
    """
    from config import app_settings

    if app_settings.OCR_PYTHON:
        return app_settings.OCR_PYTHON
    if platform.system() == "Windows":
        return r"D:\61.tool\common\ocr\venv\Scripts\python.exe"
    return str(Path.home() / ".venv" / "ocr" / "bin" / "python")


_OCR_WORKER_SCRIPT = Path(__file__).parent / "ocr_worker.py"
_STREAM_END = object()


class PageText(TypedDict):
    page_no: int  # 1-indexed
    full_text: str
    char_count: int


class OcrPageResult(PageText):
    image_sha256: str
    state: str
    raw_output: str
    block_count: int
    quality_flags: list[str]
    ink_coverage: float | None
    attempt_count: int
    server_generation: NotRequired[int]
    error_message: NotRequired[str | None]
    layout_type: NotRequired[str]
    primary_text: NotRequired[str | None]
    external_text: NotRequired[str | None]
    selected_engine: NotRequired[str]


def _read_worker_output(stream: Iterator[str], events: queue.Queue[object]) -> None:
    try:
        for line in stream:
            events.put(line)
    except BaseException as exc:
        events.put(exc)
    finally:
        events.put(_STREAM_END)


def _stop_worker_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _ocr_worker_env() -> dict[str, str]:
    from config import app_settings

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "OCR_ENGINE": app_settings.OCR_ENGINE}
    values = {
        "OCR_PATH": app_settings.OCR_PACKAGE_PATH,
        "SURYA_INFERENCE_URL": app_settings.SURYA_INFERENCE_URL,
        "SURYA_MODEL": app_settings.SURYA_MODEL,
        "SURYA_LLAMA_SERVER_PATH": app_settings.SURYA_LLAMA_SERVER_PATH,
        "SURYA_MODEL_PATH": app_settings.SURYA_MODEL_PATH,
        "SURYA_MMPROJ_PATH": app_settings.SURYA_MMPROJ_PATH,
        "SURYA_REQUEST_TIMEOUT_SEC": app_settings.SURYA_REQUEST_TIMEOUT_SEC,
        "SURYA_MAX_ATTEMPTS": app_settings.SURYA_MAX_ATTEMPTS,
        "OCR_QUALITY_MIN_INK_COVERAGE": app_settings.OCR_QUALITY_MIN_INK_COVERAGE,
        "OCR_SERVER_MAX_PAGES": app_settings.OCR_SERVER_MAX_PAGES,
        "OCR_SERVER_CONSECUTIVE_FAILURES": app_settings.OCR_SERVER_CONSECUTIVE_FAILURES,
        "OCR_SERVER_FAILURE_WINDOW": app_settings.OCR_SERVER_FAILURE_WINDOW,
        "OCR_SERVER_FAILURE_RATE": app_settings.OCR_SERVER_FAILURE_RATE,
        "OCR_CROSSCHECK_ALL_PAGES": app_settings.OCR_CROSSCHECK_ALL_PAGES,
        "OCR_CROSS_ENGINE_MIN_SIMILARITY": app_settings.OCR_CROSS_ENGINE_MIN_SIMILARITY,
        "OCR_EXTERNAL_CONFIDENCE_MEDIAN": app_settings.OCR_EXTERNAL_CONFIDENCE_MEDIAN,
        "OCR_EXTERNAL_CONFIDENCE_WEIGHTED_MEAN": app_settings.OCR_EXTERNAL_CONFIDENCE_WEIGHTED_MEAN,
        "OCR_EXTERNAL_LOW_CONFIDENCE_CHAR_RATIO": app_settings.OCR_EXTERNAL_LOW_CONFIDENCE_CHAR_RATIO,
    }
    for key, value in values.items():
        if value is not None:
            env[key] = str(value)
    return env


def iter_ocr_pages(
    tasks: list[OcrTask],
    *,
    progress_callback: Callable[[OcrProgressEvent], None] | None = None,
    inactivity_timeout_sec: float | None = None,
) -> Iterator[tuple[str, OcrPageResult]]:
    """Run the isolated worker and yield one durable result candidate per page."""
    if not tasks:
        return
    if inactivity_timeout_sec is None:
        from config import app_settings

        inactivity_timeout_sec = app_settings.OCR_WORKER_INACTIVITY_TIMEOUT_SEC
    if inactivity_timeout_sec <= 0:
        raise ValueError("OCR worker inactivity timeout must be positive")
    manifest_path: Path | None = None
    proc: subprocess.Popen[str] | None = None
    reader: threading.Thread | None = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as manifest:
            json.dump({"tasks": tasks}, manifest, ensure_ascii=False)
            manifest_path = Path(manifest.name)

        cmd = [_resolve_ocr_python(), str(_OCR_WORKER_SCRIPT), "--manifest", str(manifest_path)]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=_ocr_worker_env(),
        )
        assert proc.stdout is not None
        events: queue.Queue[object] = queue.Queue()
        reader = threading.Thread(
            target=_read_worker_output,
            args=(proc.stdout, events),
            name="ocr-worker-stdout",
            daemon=True,
        )
        reader.start()
        while True:
            try:
                event = events.get(timeout=inactivity_timeout_sec)
            except queue.Empty as exc:
                _stop_worker_process(proc)
                raise RuntimeError(
                    f"OCR worker produced no output for {inactivity_timeout_sec:g} seconds"
                ) from exc
            if event is _STREAM_END:
                break
            if isinstance(event, BaseException):
                raise RuntimeError("OCR worker stdout reader failed") from event
            if not isinstance(event, str):
                raise RuntimeError("OCR worker stdout reader returned an invalid event")
            line = event
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if data.get("event") == "fatal":
                raise RuntimeError(f"OCR worker error: {data.get('error', 'unknown error')}")
            if data.get("event") == "progress":
                if progress_callback is not None:
                    progress_callback(data["progress"])
                continue
            if data.get("event") != "page":
                raise RuntimeError(f"unknown OCR worker event: {data.get('event')}")
            yield str(data["book_name"]), data["page"]

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"OCR worker exited with code {proc.returncode}")
    finally:
        if proc is not None:
            _stop_worker_process(proc)
        if reader is not None:
            reader.join(timeout=1)
        if manifest_path is not None:
            manifest_path.unlink(missing_ok=True)


def run_ocr_subprocess(images_dirs: list[Path]) -> Iterator[tuple[str, list[PageText]]]:
    """Compatibility collector returning completed page text by book."""
    tasks: list[OcrTask] = []
    order: list[str] = []
    for images_dir in images_dirs:
        order.append(images_dir.name)
        for image_path in sorted(images_dir.glob("*.png")):
            if image_path.stem.isdigit():
                tasks.append(
                    {"book_name": images_dir.name, "page_no": int(image_path.stem), "image_path": str(image_path)}
                )

    collected: dict[str, list[PageText]] = {book_name: [] for book_name in order}
    for book_name, page in iter_ocr_pages(tasks):
        if page["state"] != "passed":
            raise RuntimeError(
                f"OCR quality gate failed for '{book_name}' page {page['page_no']}: "
                f"{page.get('error_message') or ', '.join(page['quality_flags'])}"
            )
        collected.setdefault(book_name, []).append(
            {"page_no": page["page_no"], "full_text": page["full_text"], "char_count": page["char_count"]}
        )
    for book_name in order:
        yield book_name, sorted(collected.get(book_name, []), key=lambda page: page["page_no"])


def extract_pages(pdf_path: str | Path) -> list[PageText]:
    pages: list[PageText] = []
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc):  # type: ignore[arg-type]
            blocks = page.get_text("blocks")
            parts: list[str] = []
            for b in blocks:
                # blocks タプルの 5 要素目がテキスト本体（PyMuPDF API）
                cleaned = _NEWLINE_RE.sub("", b[4]).strip()
                if cleaned:
                    parts.append(cleaned)
            full_text = "\n".join(parts)
            pages.append(
                {
                    "page_no": i + 1,
                    "full_text": full_text,
                    "char_count": len(full_text),
                }
            )
    return pages
