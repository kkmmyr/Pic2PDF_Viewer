"""Page-level OCR engine adapters used by the standalone worker."""

from __future__ import annotations

import hashlib
import inspect
import io
import os
import platform
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PIL import Image

try:
    from .ocr_candidate_selection import (
        is_external_materially_more_complete,
        is_external_safe_repetition_fallback,
    )
    from .ocr_content_guards import has_suspicious_repetition
    from .ocr_layout_types import suggest_layout_type
    from .ocr_worker_protocol import OcrWorkerTask, emit, failed_payload, page_payload
    from .surya_quality import crosscheck_ocr_results, evaluate_external_ocr
    from .surya_runtime import SuryaClient
    from .surya_types import SuryaPageResult
except ImportError:
    from ocr_candidate_selection import (
        is_external_materially_more_complete,
        is_external_safe_repetition_fallback,
    )
    from ocr_content_guards import has_suspicious_repetition
    from ocr_layout_types import suggest_layout_type
    from ocr_worker_protocol import OcrWorkerTask, emit, failed_payload, page_payload
    from surya_quality import crosscheck_ocr_results, evaluate_external_ocr
    from surya_runtime import SuryaClient
    from surya_types import SuryaPageResult

_YOMITOKU_ADJUDICATION_FLAGS = {
    "duplicate_text_recovery",
    "sparse_page_block_fallback",
    "sparse_page_variant_consensus",
}
_YOMITOKU_DEVICE_VALUES = frozenset({"auto", "cuda", "mps", "cpu"})


def _requested_yomitoku_device() -> str:
    """Return and validate the device requested by the OCR runtime contract."""
    requested = os.environ.get("OCR_YOMITOKU_DEVICE", "auto").strip().casefold()
    if requested not in _YOMITOKU_DEVICE_VALUES:
        allowed = ", ".join(sorted(_YOMITOKU_DEVICE_VALUES))
        raise ValueError(f"invalid OCR_YOMITOKU_DEVICE={requested!r}; expected one of: {allowed}")
    return requested


def _initialize_yomitoku_engine(engine: Any) -> None:
    """Initialize an external YomiToku wrapper without silently falling back on Mac."""
    requested = _requested_yomitoku_device()
    initialize = engine.initialize
    try:
        parameters = inspect.signature(initialize).parameters.values()
    except (TypeError, ValueError):
        parameters = ()
    accepts_device = any(
        parameter.name == "device" or parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters
    )
    accepts_use_gpu = any(
        parameter.name == "use_gpu" or parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters
    )
    if accepts_device:
        initialize(device=requested)
        return
    if requested == "mps" or (requested == "auto" and platform.system() == "Darwin"):
        raise RuntimeError(
            "Mac YomiToku requires an external OCR wrapper with initialize(device=...). "
            "Update ocr_engine.py before using MPS."
        )
    if requested == "auto":
        if accepts_use_gpu:
            initialize(use_gpu=True)
        else:
            initialize()
        return
    if not accepts_use_gpu:
        raise RuntimeError("YomiToku wrapper must accept initialize(device=...) or initialize(use_gpu=...).")
    if requested == "cpu":
        initialize(use_gpu=False)
    elif requested == "cuda":
        initialize(use_gpu=True)


@dataclass(frozen=True)
class SuryaTaskExecution:
    book_name: str
    page_no: int
    image_sha256: str
    result: SuryaPageResult
    surya_failed: bool
    primary_text: str
    external_text: str | None
    layout_type: str
    selected_engine: str


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
    if layout_type == "normal_prose" and is_external_safe_repetition_fallback(
        primary.full_text,
        external.full_text,
    ):
        return (
            replace(
                external,
                state="passed",
                quality_flags=[
                    *external.quality_flags,
                    "external_recovered_primary_repetition",
                ],
                error_message=None,
            ),
            "external",
        )
    if (
        layout_type == "normal_prose"
        and primary.state == "passed"
        and external.state != "passed"
        and is_external_materially_more_complete(
            primary.full_text,
            external.full_text,
        )
        and not has_suspicious_repetition(external.full_text)
    ):
        return (
            replace(
                external,
                state="passed",
                quality_flags=[
                    *external.quality_flags,
                    "external_low_confidence_more_complete_candidate",
                ],
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


def read_image(path: Path) -> tuple[bytes, str, Image.Image]:
    image_bytes = path.read_bytes()
    image_sha256 = hashlib.sha256(image_bytes).hexdigest()
    image = Image.open(io.BytesIO(image_bytes))
    image.load()
    return image_bytes, image_sha256, image.convert("RGB")


class YomitokuAdjudicator:
    def __init__(self, quality_kwargs: dict[str, float]) -> None:
        self._quality_kwargs = quality_kwargs
        self._engine: Any | None = None

    def evaluate(
        self,
        image: Image.Image,
        surya_result: SuryaPageResult,
        *,
        min_ink_coverage: float,
    ) -> SuryaPageResult:
        engine = self._get_engine()
        import numpy as np

        items = engine.extract_text(np.asarray(image))
        return evaluate_external_ocr(
            image,
            items,
            min_ink_coverage=min_ink_coverage,
            attempt_count=surya_result.attempt_count + 1,
            engine_flag="yomitoku_adjudication",
            **self._quality_kwargs,
        )

    def _get_engine(self) -> Any:
        if self._engine is None:
            ocr_path = os.environ.get("OCR_PATH", r"D:\61.tool\common\ocr")
            if ocr_path not in sys.path:
                sys.path.insert(0, ocr_path)
            from ocr_engine import get_ocr_engine  # type: ignore[import-not-found]

            engine = get_ocr_engine("yomitoku")
            _initialize_yomitoku_engine(engine)
            self._engine = engine
        return self._engine


def process_surya_task(
    task: OcrWorkerTask,
    image_sha256: str,
    image: Image.Image,
    client: Any,
    adjudicator: YomitokuAdjudicator,
    *,
    max_attempts: int,
    crosscheck_all_pages: bool,
    cross_engine_min_similarity: float,
) -> SuryaTaskExecution:
    book_name = str(task["book_name"])
    page_no = int(task["page_no"])
    surya_result = client.recognize_with_quality(image, max_attempts=max_attempts)
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
    external_text: str | None = None
    selected_engine = "primary"
    if trigger_flags or crosscheck_all_pages:
        external_result = adjudicator.evaluate(
            image,
            surya_result,
            min_ink_coverage=client.min_ink_coverage,
        )
        external_text = external_result.full_text
        result, selected_engine = select_layout_ocr_result(
            surya_result,
            external_result,
            layout_type=layout_type,
            min_similarity=cross_engine_min_similarity,
        )
        if trigger_flags:
            result = SuryaClient._add_quality_flag(
                result,
                "surya_trigger_" + "+".join(trigger_flags),
            )

    return SuryaTaskExecution(
        book_name=book_name,
        page_no=page_no,
        image_sha256=image_sha256,
        result=result,
        surya_failed=surya_failed,
        primary_text=surya_result.full_text,
        external_text=external_text,
        layout_type=layout_type,
        selected_engine=selected_engine,
    )


def run_yomitoku(tasks: list[OcrWorkerTask]) -> None:
    import cv2  # type: ignore[import-untyped]
    import numpy as np

    ocr_path = os.environ.get("OCR_PATH", r"D:\61.tool\common\ocr")
    if ocr_path not in sys.path:
        sys.path.insert(0, ocr_path)
    from ocr_engine import get_ocr_engine  # type: ignore[import-not-found]

    engine = get_ocr_engine("yomitoku")
    _initialize_yomitoku_engine(engine)
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
            emit(page_payload(book_name, page_no, image_sha256, result))
        except Exception as exc:
            emit(failed_payload(book_name, page_no, image_sha256, exc))
