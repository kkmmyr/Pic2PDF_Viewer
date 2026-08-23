"""Typed JSONL protocol shared by the OCR worker and its caller."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, cast

if TYPE_CHECKING:
    try:
        from .surya_types import SuryaPageResult
    except ImportError:
        from surya_types import SuryaPageResult


class OcrWorkerTask(TypedDict):
    book_name: str
    page_no: int
    image_path: str


class OcrProgressPayload(TypedDict):
    stage: str
    server_generation: int
    total_pages: int
    book_name: NotRequired[str]
    page_no: NotRequired[int]
    attempt_count: NotRequired[int]
    detail: NotRequired[str]


def page_payload(
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
    selection_reason: str | None = None,
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
            "selection_reason": selection_reason,
        },
    }


def failed_payload(
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


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def emit_progress(
    stage: str,
    *,
    server_generation: int,
    total_pages: int,
    book_name: str | None = None,
    page_no: int | None = None,
    attempt_count: int | None = None,
    detail: str | None = None,
) -> None:
    progress: OcrProgressPayload = {
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
    emit({"event": "progress", "progress": progress})


def load_tasks(argv: list[str]) -> list[OcrWorkerTask]:
    if len(argv) == 3 and argv[1] == "--manifest":
        data = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError("OCR manifest must contain a tasks list")
        return cast(list[OcrWorkerTask], tasks)

    tasks: list[OcrWorkerTask] = []
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
