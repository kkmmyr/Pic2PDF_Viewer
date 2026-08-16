"""Standalone OCR worker executed by the isolated OCR interpreter.

Protocol: ``python ocr_worker.py --manifest <json>``. The manifest contains
book/page/image-path tasks and stdout emits one JSON object per page. stderr is
reserved for model/server logs so stdout remains machine readable.
"""

from __future__ import annotations

import os
import sys

try:
    from .ocr_worker_engines import (
        read_image as _read_image,
    )
    from .ocr_worker_engines import (
        run_yomitoku,
        select_layout_ocr_result,
    )
    from .ocr_worker_protocol import OcrWorkerTask, load_tasks
    from .ocr_worker_protocol import emit as _emit
    from .ocr_worker_session import run_surya
    from .surya_runtime import SuryaClient
    from .surya_server import SuryaServer
except ImportError:
    from ocr_worker_engines import read_image as _read_image
    from ocr_worker_engines import run_yomitoku, select_layout_ocr_result
    from ocr_worker_protocol import OcrWorkerTask, load_tasks
    from ocr_worker_protocol import emit as _emit
    from ocr_worker_session import run_surya
    from surya_runtime import SuryaClient
    from surya_server import SuryaServer

__all__ = ["main", "select_layout_ocr_result"]


def _run_surya(tasks: list[OcrWorkerTask]) -> None:
    """Compatibility seam for direct worker tests and manual diagnostics."""
    run_surya(
        tasks,
        server_factory=SuryaServer,
        client_factory=SuryaClient,
        read_image_fn=_read_image,
    )


def _run_yomitoku(tasks: list[OcrWorkerTask]) -> None:
    run_yomitoku(tasks)


def _load_tasks(argv: list[str]) -> list[OcrWorkerTask]:
    return load_tasks(argv)


def main() -> None:
    if len(sys.argv) < 2:
        _emit({"event": "fatal", "error": "no manifest or images_dirs provided"})
        raise SystemExit(1)
    try:
        tasks = _load_tasks(sys.argv)
        if not tasks:
            raise ValueError("OCR task list is empty")
        engine = os.environ.get("OCR_ENGINE", "surya2").casefold()
        if engine == "surya2":
            _run_surya(tasks)
        elif engine == "yomitoku":
            _run_yomitoku(tasks)
        else:
            raise ValueError(f"unsupported OCR_ENGINE: {engine}")
    except Exception as exc:
        _emit({"event": "fatal", "error": str(exc)})
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
