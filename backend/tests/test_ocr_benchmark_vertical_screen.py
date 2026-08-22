from __future__ import annotations

import importlib.util
import itertools
import json
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "ocr_benchmark_vertical_screen.py"
_SPEC = importlib.util.spec_from_file_location("ocr_benchmark_vertical_screen", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
screen = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(screen)

_TEXT_PATH = _SCRIPT_PATH.with_name("ocr_benchmark_text.py")
_TEXT_SPEC = importlib.util.spec_from_file_location("ocr_benchmark_text_reference", _TEXT_PATH)
assert _TEXT_SPEC is not None and _TEXT_SPEC.loader is not None
text_metrics = importlib.util.module_from_spec(_TEXT_SPEC)
_TEXT_SPEC.loader.exec_module(text_metrics)


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    _ = path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _build(
    tmp_path: Path,
    metadata: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    *,
    dataset: str = "jssoda",
    include_horizontal: bool = False,
) -> dict[str, Any]:
    metadata_path = tmp_path / "metadata.jsonl"
    predictions_path = tmp_path / "predictions.jsonl"
    _write_jsonl(metadata_path, metadata)
    _write_jsonl(predictions_path, predictions)
    return screen.build_report(
        dataset=dataset,
        metadata_path=metadata_path,
        prediction_path=predictions_path,
        engine_label="candidate",
        model_revision="revision-sha",
        prompt_id="plain-ocr-v1",
        seed="0",
        include_horizontal=include_horizontal,
    )


def test_bit_vector_edit_distance_matches_existing_contract() -> None:
    values = ["".join(characters) for length in range(4) for characters in itertools.product("ab漢", repeat=length)]

    for reference in values:
        for hypothesis in values:
            assert screen.edit_distance(reference, hypothesis) == (text_metrics._edit_distance(reference, hypothesis))


def test_jssoda_defaults_to_vertical_and_reports_column_metrics(tmp_path: Path) -> None:
    report = _build(
        tmp_path,
        [
            {"id": 1, "passage": "右列左列", "is_vertical": True, "num_columns": 2},
            {"id": 2, "passage": "横書き", "is_vertical": False, "num_columns": 1},
        ],
        [{"id": 1, "pred": "右列左例"}],
    )

    metrics = {metric["group"]: metric for metric in report["metrics"]}
    assert report["scope"] == "vertical"
    assert set(metrics) == {"overall", "direction:vertical", "vertical:columns:2"}
    assert metrics["overall"]["aggregate_cer"] == pytest.approx(1 / 4)
    assert metrics["overall"]["max_page_cer"] == pytest.approx(1 / 4)
    assert metrics["overall"]["exact_match_rate"] == 0
    assert report["pages"][0]["num_columns"] == 2


def test_jssoda_all_scope_requires_and_groups_horizontal_predictions(
    tmp_path: Path,
) -> None:
    report = _build(
        tmp_path,
        [
            {"id": "v", "passage": "縦", "is_vertical": True, "num_columns": 1},
            {"id": "h", "passage": "横", "is_vertical": False, "num_columns": 1},
        ],
        [{"id": "v", "pred": "縦"}, {"id": "h", "pred": "横"}],
        include_horizontal=True,
    )

    groups = {metric["group"] for metric in report["metrics"]}
    assert report["scope"] == "all"
    assert "direction:horizontal" in groups
    assert "horizontal:columns:1" in groups


def test_vjroda_removes_reference_markup_and_records_provenance(tmp_path: Path) -> None:
    report = _build(
        tmp_path,
        [{"id": 8, "text": "<header>題</header>本 文<footer>頁</footer>"}],
        [{"id": 8, "pred": "題本文頁"}],
        dataset="vjroda",
    )

    assert report["metrics"][0]["aggregate_cer"] == 0
    assert report["model_revision"] == "revision-sha"
    assert report["prompt_id"] == "plain-ocr-v1"
    assert report["seed"] == "0"
    assert len(report["inputs"]["metadata_sha256"]) == 64
    assert len(report["inputs"]["predictions_sha256"]) == 64


@pytest.mark.parametrize(
    ("metadata", "predictions", "message"),
    [
        (
            [
                {"id": 1, "passage": "a", "is_vertical": True, "num_columns": 1},
                {"id": 1, "passage": "b", "is_vertical": True, "num_columns": 1},
            ],
            [{"id": 1, "pred": "a"}],
            "duplicate id",
        ),
        (
            [{"id": 1, "passage": "a", "is_vertical": True, "num_columns": 1}],
            [{"id": 2, "pred": "a"}],
            "coverage mismatch",
        ),
        (
            [{"id": 1, "passage": "a", "is_vertical": True, "num_columns": 1}],
            [{"id": 1, "pred": None}],
            "no string pred",
        ),
    ],
)
def test_invalid_public_screening_inputs_fail_closed(
    tmp_path: Path,
    metadata: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _ = _build(tmp_path, metadata, predictions)


def test_main_writes_audit_report(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.jsonl"
    predictions_path = tmp_path / "predictions.jsonl"
    output_path = tmp_path / "report.json"
    _write_jsonl(
        metadata_path,
        [{"id": 1, "passage": "本文", "is_vertical": True, "num_columns": 1}],
    )
    _write_jsonl(predictions_path, [{"id": 1, "pred": "本文"}])

    exit_code = screen.main(
        [
            "--dataset",
            "jssoda",
            "--metadata",
            str(metadata_path),
            "--predictions",
            str(predictions_path),
            "--output",
            str(output_path),
            "--engine-label",
            "candidate",
            "--model-revision",
            "revision-sha",
            "--prompt-id",
            "plain-ocr-v1",
            "--seed",
            "0",
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["pages"][0]["exact_match"]
