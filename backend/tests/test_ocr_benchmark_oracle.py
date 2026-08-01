from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "compare_ocr_benchmarks.py"
_SPEC = importlib.util.spec_from_file_location("compare_ocr_benchmarks", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
oracle = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(oracle)


def _entry() -> dict:
    return {
        "id": 1,
        "run_id": 10,
        "page_no": 2,
        "page_type": "narrative",
        "layout_type": "normal_prose",
        "reference_text": "ABC",
        "image_sha256": "sha",
        "state": "verified",
    }


def _report(engine: str, hypothesis: str, image_sha256: str = "sha") -> dict:
    return {
        "engine": engine,
        "pages": [
            {
                "entry_id": 1,
                "image_sha256": image_sha256,
                "hypothesis": hypothesis,
            }
        ],
    }


def test_reference_position_oracle_unions_complementary_candidates() -> None:
    result = oracle.compare_reports(
        {"entries": [_entry()]},
        [_report("candidate-a", "AXC"), _report("candidate-b", "ABX")],
    )

    page_oracle = result["page_oracle"]["pages"][0]
    reference_oracle = result["reference_position_oracle"]["pages"][0]
    assert page_oracle["edit_distance"] == 1
    assert page_oracle["selected_engine"] == "candidate-a"
    assert reference_oracle["misses"] == 0
    assert reference_oracle["miss_rate"] == 0
    assert reference_oracle["candidate_edit_distances"] == {
        "candidate-a": 1,
        "candidate-b": 1,
    }


def test_compare_reports_rejects_image_mismatch() -> None:
    with pytest.raises(ValueError, match="image SHA-256 mismatch"):
        oracle.compare_reports(
            {"entries": [_entry()]},
            [_report("candidate-a", "ABC"), _report("candidate-b", "ABC", "bad")],
        )


def test_compare_reports_scopes_corpus_to_primary_report() -> None:
    unused = {**_entry(), "id": 2, "image_sha256": "unused"}

    result = oracle.compare_reports(
        {"entries": [_entry(), unused]},
        [_report("candidate-a", "ABC"), _report("candidate-b", "ABC")],
    )

    assert [page["entry_id"] for page in result["page_oracle"]["pages"]] == [1]
