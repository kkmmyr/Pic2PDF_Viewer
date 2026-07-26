from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "benchmark_ocr_ground_truth.py"
_SPEC = importlib.util.spec_from_file_location("benchmark_ocr_ground_truth", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
benchmark = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(benchmark)


def test_summarize_calculates_weighted_metrics_by_page_type() -> None:
    entries = [
        {
            "id": 1,
            "run_id": 10,
            "page_no": 2,
            "page_type": "narrative",
            "reference_text": "abcdef",
            "image_sha256": "a",
        },
        {
            "id": 2,
            "run_id": 10,
            "page_no": 3,
            "page_type": "toc",
            "reference_text": "目 次",
            "image_sha256": "b",
        },
    ]
    report = benchmark.summarize(entries, {1: "abcxef", 2: "目次"}, "test")

    assert report["engine"] == "test"
    assert report["pages"][0]["cer"] == pytest.approx(1 / 6)
    metrics = {metric["group"]: metric for metric in report["metrics"]}
    assert metrics["overall"]["page_count"] == 2
    assert metrics["overall"]["total_edit_distance"] == 1
    assert metrics["overall"]["total_reference_chars"] == 8
    assert metrics["overall"]["aggregate_cer"] == pytest.approx(1 / 8)
    assert metrics["narrative"]["aggregate_cer"] == pytest.approx(1 / 6)
    assert metrics["toc"]["aggregate_cer"] == 0
