from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "select_qwen35_dots_predictions.py"
_SPEC = importlib.util.spec_from_file_location("select_qwen35_dots_predictions", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
select = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = select
_SPEC.loader.exec_module(select)


def _record(record_id: str, pred: str, *, engine: str) -> dict[str, Any]:
    return {
        "id": record_id,
        "pred": pred,
        "input_sha256": f"sha-{record_id}",
        "model_revision": f"{engine}-revision",
        "model_fingerprint": f"{engine}-fingerprint",
        "prompt_id": f"{engine}-prompt",
        "raw_response": (f'<div data-bbox="0 0 10 10" data-label="Text"><p>{pred}</p></div>'),
    }


def _write(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_selector_uses_qwen_unless_candidate_only_flags_require_dots(
    tmp_path: Path,
) -> None:
    repeated = "反復文字列です長さを確保" * 8
    clean = _record("clean", "正常本文", engine="qwen")
    clean.update(html_truncated=False, suspicious_repetition=False)
    looping = _record("loop", repeated, engine="qwen")
    looping.update(html_truncated=True, suspicious_repetition=True)
    fallback = _record("loop", "dotsの正常本文", engine="dots")
    qwen_path = tmp_path / "qwen.jsonl"
    dots_path = tmp_path / "dots.jsonl"
    _write(qwen_path, [clean, looping])
    _write(dots_path, [_record("clean", "dotsの正常本文", engine="dots"), fallback])

    selected = select.select_predictions(qwen_path=qwen_path, dots_path=dots_path)

    assert [record["id"] for record in selected] == ["clean", "loop"]
    assert selected[0]["selected_engine"] == "qwen3.5-ocr-jp-2b"
    assert selected[0]["selection_reason"] == "qwen_clean"
    assert selected[1]["selected_engine"] == "dots.mocr"
    assert selected[1]["pred"] == "dotsの正常本文"
    assert selected[1]["selection_reason"] == "suspicious_repetition+html_truncated"


def test_selector_uses_unsupported_markup_as_candidate_only_signal(
    tmp_path: Path,
) -> None:
    qwen = _record("styled", "とが提供する価値", engine="qwen")
    qwen.update(html_truncated=False, suspicious_repetition=False)
    qwen["raw_response"] = '<div data-bbox="0 0 10 10" data-label="Text"><p><i>とが提供する価値</i></p></div>'
    fallback = _record("styled", "AIが提供する価値", engine="dots")
    qwen_path = tmp_path / "qwen.jsonl"
    dots_path = tmp_path / "dots.jsonl"
    _write(qwen_path, [qwen])
    _write(dots_path, [fallback])

    selected = select.select_predictions(qwen_path=qwen_path, dots_path=dots_path)

    assert selected[0]["selected_engine"] == "dots.mocr"
    assert selected[0]["selection_reason"] == "unsupported_markup:i"


def test_selector_uses_suspicious_vertical_bbox_order_signal(tmp_path: Path) -> None:
    qwen = _record("order", "段落一段落二", engine="qwen")
    qwen.update(html_truncated=False, suspicious_repetition=False)
    qwen["raw_response"] = (
        '<div data-bbox="100 700 400 940" data-label="Text"><p>段落二</p></div>'
        '<div data-bbox="600 700 900 940" data-label="Text"><p>段落一</p></div>'
    )
    dots = _record("order", "段落一段落二", engine="dots")
    qwen_path = tmp_path / "qwen.jsonl"
    dots_path = tmp_path / "dots.jsonl"
    _write(qwen_path, [qwen])
    _write(dots_path, [dots])

    selected = select.select_predictions(qwen_path=qwen_path, dots_path=dots_path)

    assert selected[0]["selected_engine"] == "dots.mocr"
    assert selected[0]["selection_reason"] == "suspicious_vertical_bbox_order"


def test_selector_rejects_missing_or_extra_secondary_predictions(
    tmp_path: Path,
) -> None:
    qwen = _record("clean", "正常本文", engine="qwen")
    qwen.update(html_truncated=False, suspicious_repetition=False)
    qwen_path = tmp_path / "qwen.jsonl"
    dots_path = tmp_path / "dots.jsonl"
    _write(qwen_path, [qwen])
    _write(
        dots_path,
        [
            _record("clean", "正常な候補", engine="dots"),
            _record("extra", "余分な候補", engine="dots"),
        ],
    )

    with pytest.raises(ValueError, match="non-qwen ids"):
        select.select_predictions(qwen_path=qwen_path, dots_path=dots_path)

    repeated = "反復文字列です長さを確保" * 8
    qwen["pred"] = repeated
    qwen["suspicious_repetition"] = True
    _write(qwen_path, [qwen])
    _write(dots_path, [])
    with pytest.raises(ValueError, match="missing qwen ids"):
        select.select_predictions(qwen_path=qwen_path, dots_path=dots_path)


def test_selector_rejects_mixed_candidate_provenance(tmp_path: Path) -> None:
    first = _record("first", "第一本文", engine="qwen")
    first.update(html_truncated=False, suspicious_repetition=False)
    second = _record("second", "第二本文", engine="qwen")
    second.update(html_truncated=False, suspicious_repetition=False)
    second["model_revision"] = "different-revision"
    qwen_path = tmp_path / "qwen.jsonl"
    dots_path = tmp_path / "dots.jsonl"
    _write(qwen_path, [first, second])
    _write(
        dots_path,
        [
            _record("first", "第一候補", engine="dots"),
            _record("second", "第二候補", engine="dots"),
        ],
    )

    with pytest.raises(ValueError, match="qwen predictions mix"):
        select.select_predictions(qwen_path=qwen_path, dots_path=dots_path)


def test_selector_uses_non_repeating_materially_longer_dots_candidate(
    tmp_path: Path,
) -> None:
    qwen_text = "".join(chr(0x4E00 + index) for index in range(300))
    dots_text = qwen_text + "".join(chr(0x6000 + index) for index in range(40))
    qwen = _record("omission", qwen_text, engine="qwen")
    qwen.update(html_truncated=False, suspicious_repetition=False)
    dots = _record("omission", dots_text, engine="dots")
    qwen_path = tmp_path / "qwen.jsonl"
    dots_path = tmp_path / "dots.jsonl"
    _write(qwen_path, [qwen])
    _write(dots_path, [dots])

    selected = select.select_predictions(qwen_path=qwen_path, dots_path=dots_path)

    assert selected[0]["selected_engine"] == "dots.mocr"
    assert selected[0]["selection_reason"] == "dots_materially_more_complete"
    assert selected[0]["primary_text"] == qwen["pred"]
    assert selected[0]["external_text"] == dots["pred"]


def test_selector_recomputes_repetition_and_rejects_input_mismatch(
    tmp_path: Path,
) -> None:
    repeated = "反復文字列です長さを確保" * 8
    qwen = _record("loop", repeated, engine="qwen")
    qwen.update(html_truncated=False, suspicious_repetition=False)
    qwen_path = tmp_path / "qwen.jsonl"
    dots_path = tmp_path / "dots.jsonl"
    _write(qwen_path, [qwen])
    _write(dots_path, [_record("loop", "正常な候補", engine="dots")])

    with pytest.raises(ValueError, match="repetition flag mismatch"):
        select.select_predictions(qwen_path=qwen_path, dots_path=dots_path)

    qwen["suspicious_repetition"] = True
    fallback = _record("loop", "正常なfallback", engine="dots")
    fallback["input_sha256"] = "different-image"
    _write(qwen_path, [qwen])
    _write(dots_path, [fallback])
    with pytest.raises(ValueError, match="input_sha256 mismatch"):
        select.select_predictions(qwen_path=qwen_path, dots_path=dots_path)


def test_main_writes_atomic_jsonl(tmp_path: Path) -> None:
    qwen = _record("clean", "正常本文", engine="qwen")
    qwen.update(html_truncated=False, suspicious_repetition=False)
    qwen_path = tmp_path / "qwen.jsonl"
    dots_path = tmp_path / "dots.jsonl"
    output_path = tmp_path / "selected.jsonl"
    _write(qwen_path, [qwen])
    _write(dots_path, [_record("clean", "dots本文", engine="dots")])

    assert (
        select.main(
            [
                "--qwen-predictions",
                str(qwen_path),
                "--dots-predictions",
                str(dots_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    assert json.loads(output_path.read_text(encoding="utf-8"))["pred"] == "正常本文"
