from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "paddle_ocr_worker.py"
_SPEC = importlib.util.spec_from_file_location("paddle_ocr_worker", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
worker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(worker)


def test_order_segments_uses_right_to_left_order_for_vertical_page() -> None:
    segments = worker.order_segments(
        ["左列", "右列"],
        [
            [[10, 0], [20, 0], [20, 100], [10, 100]],
            [[90, 0], [100, 0], [100, 100], [90, 100]],
        ],
        [0.8, 0.9],
    )

    assert [segment["text"] for segment in segments] == ["右列", "左列"]
    assert all(segment["is_vertical"] for segment in segments)
    assert "center_x" not in segments[0]
