"""YomiToku device initialization compatibility helpers."""

from __future__ import annotations

import inspect
import os
from typing import Any

_DEVICE_VALUES = frozenset({"auto", "cuda", "mps", "cpu"})


def requested_yomitoku_device() -> str:
    requested = os.environ.get("OCR_YOMITOKU_DEVICE", "auto").strip().casefold()
    if requested not in _DEVICE_VALUES:
        allowed = ", ".join(sorted(_DEVICE_VALUES))
        raise ValueError(f"invalid OCR_YOMITOKU_DEVICE={requested!r}; expected one of: {allowed}")
    return requested


def initialize_yomitoku_engine(engine: Any, *, requested: str, system_name: str) -> None:
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
    if requested == "mps" or (requested == "auto" and system_name == "Darwin"):
        raise RuntimeError(
            "Mac YomiToku requires an external OCR wrapper with initialize(device=...). "
            "Update ocr_engine.py before using MPS."
        )
    if requested == "auto":
        initialize(use_gpu=True) if accepts_use_gpu else initialize()
        return
    if not accepts_use_gpu:
        raise RuntimeError("YomiToku wrapper must accept initialize(device=...) or initialize(use_gpu=...).")
    initialize(use_gpu=requested == "cuda")
