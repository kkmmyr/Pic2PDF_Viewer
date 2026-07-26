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
from dataclasses import replace
from pathlib import Path
from typing import Any

from PIL import Image

try:
    from .surya_ocr import (
        OcrSessionPolicy,
        SuryaClient,
        SuryaPageResult,
        SuryaServer,
        crosscheck_ocr_results,
        evaluate_external_ocr,
    )
except ImportError:
    from surya_ocr import (
        OcrSessionPolicy,
        SuryaClient,
        SuryaPageResult,
        SuryaServer,
        crosscheck_ocr_results,
        evaluate_external_ocr,
    )

try:
    from .ocr_layout_types import suggest_layout_type
except ImportError:
    from ocr_layout_types import suggest_layout_type

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
    server_generation: int | None = None,
    *,
    layout_type: str = "unknown",
    primary_text: str | None = None,
    external_text: str | None = None,
    selected_engine: str = "primary",
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
            "server_generation": server_generation,
            "error_message": result.error_message,
            "layout_type": layout_type,
            "primary_text": primary_text if primary_text is not None else result.full_text,
            "external_text": external_text,
            "selected_engine": selected_engine,
        },
    }


def _failed_payload(
    book_name: str,
    page_no: int,
    image_sha256: str,
    exc: Exception,
    server_generation: int | None = None,
) -> dict[str, Any]:
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
            "server_generation": server_generation,
            "error_message": str(exc),
        },
    }


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _emit_progress(
    stage: str,
    *,
    server_generation: int,
    total_pages: int,
    book_name: str | None = None,
    page_no: int | None = None,
    attempt_count: int | None = None,
    detail: str | None = None,
) -> None:
    progress = {
        "stage": stage,
        "server_generation": server_generation,
        "total_pages": total_pages,
    }
    if book_name is not None:
        progress["book_name"] = book_name
    if page_no is not None:
        progress["page_no"] = page_no
    if attempt_count is not None:
        progress["attempt_count"] = attempt_count
    if detail is not None:
        progress["detail"] = detail
    _emit({"event": "progress", "progress": progress})


def select_layout_ocr_result(
    primary: SuryaPageResult,
    external: SuryaPageResult,
    *,
    layout_type: str,
    min_similarity: float,
) -> tuple[SuryaPageResult, str]:
    """Select a machine candidate while retaining QA-visible disagreement."""
    external_is_materially_more_complete = external.char_count >= max(1, primary.char_count) * 1.02
    if (
        layout_type == "mixed_illustration"
        and external.state == "passed"
        and (primary.state != "passed" or external_is_materially_more_complete)
    ):
        return (
            replace(
                external,
                quality_flags=[*external.quality_flags, "layout_selected_external"],
                error_message=None,
            ),
            "external",
        )
    selected = crosscheck_ocr_results(primary, external, min_similarity=min_similarity)
    selected_engine = (
        "external"
        if selected.full_text == external.full_text and selected.full_text != primary.full_text
        else "primary"
    )
    return selected, selected_engine


def _read_image(path: Path) -> tuple[bytes, str, Image.Image]:
    image_bytes = path.read_bytes()
    image_sha256 = hashlib.sha256(image_bytes).hexdigest()
    image = Image.open(io.BytesIO(image_bytes))
    image.load()
    return image_bytes, image_sha256, image.convert("RGB")


def _run_surya(tasks: list[dict[str, Any]]) -> None:
    base_url = os.environ.get("SURYA_INFERENCE_URL", "http://127.0.0.1:8768/v1")
    server_kwargs = {
        "executable": os.environ.get("SURYA_LLAMA_SERVER_PATH"),
        "model_path": os.environ.get("SURYA_MODEL_PATH"),
        "mmproj_path": os.environ.get("SURYA_MMPROJ_PATH"),
    }
    client_kwargs = {
        "model": os.environ.get("SURYA_MODEL", "surya-ocr-2"),
        "timeout_sec": float(os.environ.get("SURYA_REQUEST_TIMEOUT_SEC", "600")),
        "min_ink_coverage": float(os.environ.get("OCR_QUALITY_MIN_INK_COVERAGE", "0.85")),
    }
    max_attempts = int(os.environ.get("SURYA_MAX_ATTEMPTS", "3"))
    policy_kwargs = {
        "max_pages": int(os.environ.get("OCR_SERVER_MAX_PAGES", "24")),
        "consecutive_failure_limit": int(os.environ.get("OCR_SERVER_CONSECUTIVE_FAILURES", "2")),
        "failure_window": int(os.environ.get("OCR_SERVER_FAILURE_WINDOW", "8")),
        "failure_rate": float(os.environ.get("OCR_SERVER_FAILURE_RATE", "0.5")),
    }
    crosscheck_all_pages = os.environ.get("OCR_CROSSCHECK_ALL_PAGES", "true").lower() in {"1", "true", "yes"}
    cross_engine_min_similarity = float(os.environ.get("OCR_CROSS_ENGINE_MIN_SIMILARITY", "0.85"))
    external_quality_kwargs = {
        "min_median_confidence": float(os.environ.get("OCR_EXTERNAL_CONFIDENCE_MEDIAN", "0.85")),
        "min_weighted_mean_confidence": float(os.environ.get("OCR_EXTERNAL_CONFIDENCE_WEIGHTED_MEAN", "0.75")),
        "max_low_confidence_char_ratio": float(os.environ.get("OCR_EXTERNAL_LOW_CONFIDENCE_CHAR_RATIO", "0.25")),
    }
    yomitoku_engine: Any | None = None
    task_index = 0
    server_generation = 0
    total_pages = len(tasks)
    while task_index < total_pages:
        server_generation += 1
        policy = OcrSessionPolicy(**policy_kwargs)
        restart_reason = "completed"
        with SuryaServer(base_url, **server_kwargs) as server:
            server_owned = server.owns_process
            _emit_progress(
                "server_started",
                server_generation=server_generation,
                total_pages=total_pages,
                detail="worker_owned" if server_owned else "external",
            )
            client = SuryaClient(base_url, **client_kwargs)
            while task_index < total_pages:
                task = tasks[task_index]
                task_index += 1
                surya_failed = True
                result: SuryaPageResult | None = None
                primary_text: str | None = None
                external_text: str | None = None
                layout_type = "unknown"
                selected_engine = "primary"
                attempt_count: int | None = None
                book_name = str(task["book_name"])
                page_no = int(task["page_no"])
                image_path = Path(task["image_path"])
                image_sha256 = ""
                _emit_progress(
                    "page_started",
                    server_generation=server_generation,
                    total_pages=total_pages,
                    book_name=book_name,
                    page_no=page_no,
                )
                try:
                    _, image_sha256, image = _read_image(image_path)
                    surya_result = client.recognize_with_quality(image, max_attempts=max_attempts)
                    primary_text = surya_result.full_text
                    layout_type = suggest_layout_type(
                        raw_output=surya_result.raw_output,
                        full_text=surya_result.full_text,
                        char_count=surya_result.char_count,
                    )
                    surya_failed = surya_result.state == "failed"
                    trigger_flags = sorted(set(surya_result.quality_flags) & _YOMITOKU_ADJUDICATION_FLAGS)
                    if surya_failed:
                        trigger_flags.append("surya_failed")
                    result = surya_result
                    if trigger_flags or crosscheck_all_pages:
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
                            attempt_count=surya_result.attempt_count + 1,
                            engine_flag="yomitoku_adjudication",
                            **external_quality_kwargs,
                        )
                        external_text = result.full_text
                        result, selected_engine = select_layout_ocr_result(
                            surya_result,
                            result,
                            layout_type=layout_type,
                            min_similarity=cross_engine_min_similarity,
                        )
                        if trigger_flags:
                            result = SuryaClient._add_quality_flag(
                                result,
                                "surya_trigger_" + "+".join(trigger_flags),
                            )
                    attempt_count = result.attempt_count
                    _emit(
                        _page_payload(
                            book_name,
                            page_no,
                            image_sha256,
                            result,
                            server_generation,
                            layout_type=layout_type,
                            primary_text=primary_text,
                            external_text=external_text,
                            selected_engine=selected_engine,
                        )
                    )
                except Exception as exc:
                    _emit(_failed_payload(book_name, page_no, image_sha256, exc, server_generation))
                _emit_progress(
                    "page_completed",
                    server_generation=server_generation,
                    total_pages=total_pages,
                    book_name=book_name,
                    page_no=page_no,
                    attempt_count=attempt_count,
                    detail=result.state if result is not None else "worker_error",
                )
                reason = policy.record(surya_failed)
                if reason is not None and task_index < total_pages and server_owned:
                    restart_reason = reason
                    break
                if reason is not None and task_index < total_pages and not server_owned:
                    _emit_progress(
                        "server_restart_skipped",
                        server_generation=server_generation,
                        total_pages=total_pages,
                        detail=f"{reason}:external_server",
                    )
                    policy = OcrSessionPolicy(**policy_kwargs)
            _emit_progress(
                "server_stopping",
                server_generation=server_generation,
                total_pages=total_pages,
                detail=restart_reason,
            )


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
