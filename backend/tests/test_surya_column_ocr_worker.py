from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "surya_column_ocr_worker.py"
_SPEC = importlib.util.spec_from_file_location("surya_column_ocr_worker", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
worker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(worker)


def _segment(x: int, text: str, *, vertical: bool = True) -> dict:
    return {
        "text": text,
        "is_vertical": vertical,
        "bbox": [[x, 10], [x + 10, 10], [x + 10, 90], [x, 90]],
    }


def test_group_segments_keeps_vertical_source_order() -> None:
    groups = worker.group_segments(
        [_segment(90, "右"), _segment(70, "中"), _segment(50, "横", vertical=False), _segment(30, "左")],
        2,
    )

    assert [[segment["text"] for segment in group] for group in groups] == [
        ["右", "中"],
        ["左"],
    ]


def test_group_bbox_clamps_margin_to_image() -> None:
    assert worker.group_bbox([_segment(0, "端")], (100, 100), 12) == (0, 0, 23, 100)


def test_extract_surya_text_prefers_parsed_blocks() -> None:
    raw = '<div data-label="Text" data-bbox="0 0 1000 1000">本文<br>続き</div>'

    assert worker.extract_surya_text(raw) == "本文\n続き"
