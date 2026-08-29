"""YomiToku wrapper device selection for the standalone OCR worker."""

from __future__ import annotations

import inspect
import os
import platform
from typing import Any

_YOMITOKU_DEVICE_VALUES = frozenset({"auto", "cuda", "mps", "cpu"})


def requested_yomitoku_device() -> str:
    """Return and validate the device requested by the OCR runtime contract."""
    requested = os.environ.get("OCR_YOMITOKU_DEVICE", "auto").strip().casefold()
    if requested not in _YOMITOKU_DEVICE_VALUES:
        allowed = ", ".join(sorted(_YOMITOKU_DEVICE_VALUES))
        raise ValueError(f"invalid OCR_YOMITOKU_DEVICE={requested!r}; expected one of: {allowed}")
    return requested


def initialize_yomitoku_engine(engine: Any) -> None:
    """Initialize an external YomiToku wrapper without silently falling back on Mac."""
    requested = requested_yomitoku_device()
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
