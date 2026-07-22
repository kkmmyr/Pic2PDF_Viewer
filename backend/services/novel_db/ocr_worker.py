"""Standalone OCR worker executed by the isolated OCR interpreter.

Protocol: ``python ocr_worker.py --manifest <json>``.  The manifest contains
book/page/image-path tasks and stdout emits one JSON object per page.  stderr is
reserved for model/server logs so stdout remains machine readable.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

from PIL import Image
from surya_ocr import SuryaClient, SuryaPageResult, SuryaServer, evaluate_external_ocr

_YOMITOKU_ADJUDICATION_FLAGS = {
    "duplicate_text_recovery",
    "sparse_page_block_fallback",
    "sparse_page_variant_consensus",
}


def _page_payload(
    book_name: str,
    page_no: int,
    image_sha256: str,
    result: SuryaPageResult,
) -> dict[str, Any]:
    return {
        "event": "page",
        "book_name": book_name,
        "page": {
            "page_no": page_no,
            "image_sha256": image_sha256,
            "state": result.state,
            "full_text": result.full_text,
            "char_count": result.char_count,
            "raw_output": result.raw_output,
            "block_count": len(result.blocks),
            "quality_flags": result.quality_flags,
            "ink_coverage": result.ink_coverage,
            "attempt_count": result.attempt_count,
            "error_message": result.error_message,
        },
    }


def _failed_payload(book_name: str, page_no: int, image_sha256: str, exc: Exception) -> dict[str, Any]:
    return {
        "event": "page",
        "book_name": book_name,
        "page": {
            "page_no": page_no,
            "image_sha256": image_sha256,
            "state": "failed",
            "full_text": "",
            "char_count": 0,
            "raw_output": "",
            "block_count": 0,
            "quality_flags": ["worker_error"],
            "ink_coverage": None,
            "attempt_count": 0,
            "error_message": str(exc),
        },
    }


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _read_image(path: Path) -> tuple[bytes, str, Image.Image]:
    image_bytes = path.read_bytes()
    image_sha256 = hashlib.sha256(image_bytes).hexdigest()
    image = Image.open(io.BytesIO(image_bytes))
    image.load()
    return image_bytes, image_sha256, image.convert("RGB")


def _run_surya(tasks: list[dict[str, Any]]) -> None:
    base_url = os.environ.get("SURYA_INFERENCE_URL", "http://127.0.0.1:8768/v1")
    with SuryaServer(
        base_url,
        executable=os.environ.get("SURYA_LLAMA_SERVER_PATH"),
        model_path=os.environ.get("SURYA_MODEL_PATH"),
        mmproj_path=os.environ.get("SURYA_MMPROJ_PATH"),
    ):
        client = SuryaClient(
            base_url,
            model=os.environ.get("SURYA_MODEL", "surya-ocr-2"),
            timeout_sec=float(os.environ.get("SURYA_REQUEST_TIMEOUT_SEC", "600")),
            min_ink_coverage=float(os.environ.get("OCR_QUALITY_MIN_INK_COVERAGE", "0.85")),
        )
        max_attempts = int(os.environ.get("SURYA_MAX_ATTEMPTS", "3"))
        yomitoku_engine: Any | None = None
        for task in tasks:
            book_name = str(task["book_name"])
            page_no = int(task["page_no"])
            image_path = Path(task["image_path"])
            image_sha256 = ""
            try:
                _, image_sha256, image = _read_image(image_path)
                result = client.recognize_with_quality(image, max_attempts=max_attempts)
                trigger_flags = sorted(set(result.quality_flags) & _YOMITOKU_ADJUDICATION_FLAGS)
                if result.state == "failed":
                    trigger_flags.append("surya_failed")
                if trigger_flags:
                    if yomitoku_engine is None:
                        ocr_path = os.environ.get("OCR_PATH", r"D:\61.tool\common\ocr")
                        if ocr_path not in sys.path:
                            sys.path.insert(0, ocr_path)
                        from ocr_engine import get_ocr_engine  # type: ignore[import-not-found]

                        yomitoku_engine = get_ocr_engine("yomitoku")
                        yomitoku_engine.initialize()
                    import numpy as np

                    items = yomitoku_engine.extract_text(np.asarray(image))
                    result = evaluate_external_ocr(
                        image,
                        items,
                        min_ink_coverage=client.min_ink_coverage,
                        attempt_count=result.attempt_count + 1,
                        engine_flag="yomitoku_adjudication",
                    )
                    result = SuryaClient._add_quality_flag(
                        result,
                        "surya_trigger_" + "+".join(trigger_flags),
                    )
                _emit(_page_payload(book_name, page_no, image_sha256, result))
            except Exception as exc:
                _emit(_failed_payload(book_name, page_no, image_sha256, exc))


def _run_yomitoku(tasks: list[dict[str, Any]]) -> None:
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    ocr_path = os.environ.get("OCR_PATH", r"D:\61.tool\common\ocr")
    if ocr_path not in sys.path:
        sys.path.insert(0, ocr_path)
    from ocr_engine import get_ocr_engine  # type: ignore[import-not-found]

    engine = get_ocr_engine("yomitoku")
    engine.initialize()
    for task in tasks:
        book_name = str(task["book_name"])
        page_no = int(task["page_no"])
        image_path = Path(task["image_path"])
        image_sha256 = ""
        try:
            image_bytes = image_path.read_bytes()
            image_sha256 = hashlib.sha256(image_bytes).hexdigest()
            image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("image decode failed")
            results = engine.extract_text(image)
            full_text = "\n".join(item["text"] for item in results if item.get("text", "").strip())
            result = SuryaPageResult(
                full_text=full_text,
                raw_output="",
                blocks=[],
                state="passed",
                quality_flags=["legacy_yomitoku"],
                ink_coverage=None,
                attempt_count=1,
            )
            _emit(_page_payload(book_name, page_no, image_sha256, result))
        except Exception as exc:
            _emit(_failed_payload(book_name, page_no, image_sha256, exc))


def _load_tasks(argv: list[str]) -> list[dict[str, Any]]:
    if len(argv) == 3 and argv[1] == "--manifest":
        data = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError("OCR manifest must contain a tasks list")
        return tasks

    # Backward-compatible directory arguments for manual diagnostics.
    tasks: list[dict[str, Any]] = []
    for images_dir_str in argv[1:]:
        images_dir = Path(images_dir_str)
        for image_path in sorted(images_dir.glob("*.png")):
            if image_path.stem.isdigit():
                tasks.append(
                    {
                        "book_name": images_dir.name,
                        "page_no": int(image_path.stem),
                        "image_path": str(image_path),
                    }
                )
    return tasks


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
