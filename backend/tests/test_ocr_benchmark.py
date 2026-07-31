from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "benchmark_ocr_ground_truth.py"
_SPEC = importlib.util.spec_from_file_location("benchmark_ocr_ground_truth", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
benchmark = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(benchmark)


def _entry(*, reference_text: str = "茉莉花は歩く", ocr_text: str | None = None) -> dict:
    return {
        "id": 1,
        "run_id": 10,
        "page_no": 2,
        "page_type": "narrative",
        "layout_type": "normal_prose",
        "reference_text": reference_text,
        "ocr_text": reference_text if ocr_text is None else ocr_text,
        "image_sha256": "a",
        "state": "verified",
    }


def _policy() -> dict:
    return {
        "schema_version": 1,
        "name": "test policy",
        "corpus": {
            "min_verified_pages": 1,
            "min_total_reference_chars": 1,
            "min_page_type_counts": {"narrative": 1},
            "min_layout_type_counts": {"normal_prose": 1},
            "min_layout_reference_chars": {"normal_prose": 1},
        },
        "quality": {
            "aggregate_cer_max_by_group": {"layout:normal_prose": 0.005},
            "max_page_cer_by_layout": {"normal_prose": 0.01},
            "column_omission": {
                "page_type": "narrative",
                "min_deleted_chars": 2,
                "min_deletion_rate": 0.1,
                "max_suspect_pages": 0,
            },
            "proper_noun_recall_min": 1.0,
            "proper_noun_missing_occurrences_max": 0,
            "min_proper_noun_terms": 1,
            "min_proper_noun_expected_occurrences": 1,
        },
        "proper_nouns": [{"image_sha256": "a", "terms": ["茉莉花"]}],
    }


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


def test_character_error_details_counts_operations_for_omission_gate() -> None:
    details = benchmark.character_error_details("abcdef", "abcxef")

    assert details == {
        "edit_distance": 1,
        "reference_chars": 6,
        "cer": pytest.approx(1 / 6),
        "substitutions": 1,
        "deletions": 0,
        "insertions": 0,
        "deletion_rate": 0,
    }
    omission = benchmark.character_error_details("abcdefgh", "ab")
    assert omission["deletions"] == 6
    assert omission["deletion_rate"] == pytest.approx(0.75)


def test_quality_gate_passes_complete_exact_fixture() -> None:
    entry = _entry()
    corpus = {"entries": [entry]}
    report = benchmark.summarize([entry], {1: entry["ocr_text"]}, "test")

    gate = benchmark.evaluate_quality_gate(corpus, report, _policy())

    assert gate["passed"] is True
    assert all(check["passed"] for check in gate["checks"])
    assert gate["proper_noun_terms"][0]["matched_occurrences"] == 1


def test_quality_gate_reports_cer_omission_and_proper_noun_failures() -> None:
    entry = _entry(reference_text="茉莉花abcdefgh", ocr_text="ab")
    corpus = {"entries": [entry]}
    report = benchmark.summarize([entry], {1: entry["ocr_text"]}, "test")

    gate = benchmark.evaluate_quality_gate(corpus, report, _policy())
    checks = {check["name"]: check for check in gate["checks"]}

    assert gate["passed"] is False
    assert checks["quality.layout:normal_prose.aggregate_cer_max"]["passed"] is False
    assert checks["quality.layout:normal_prose.page_cer_max"]["failed_entry_ids"] == [1]
    assert checks["quality.column_omission.suspect_pages_max"]["actual"] == 1
    assert checks["quality.proper_noun.recall_min"]["actual"] == 0
    assert checks["quality.proper_noun.missing_occurrences_max"]["actual"] == 1


def test_main_returns_nonzero_for_quality_failure(tmp_path: Path) -> None:
    entry = _entry(reference_text="茉莉花abcdefgh", ocr_text="ab")
    corpus_path = tmp_path / "corpus.json"
    policy_path = tmp_path / "policy.json"
    output_path = tmp_path / "report.json"
    corpus_path.write_text(json.dumps({"entries": [entry]}, ensure_ascii=False), encoding="utf-8")
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")

    exit_code = benchmark.main(
        [
            "current",
            "--corpus-json",
            str(corpus_path),
            "--policy",
            str(policy_path),
            "--output",
            str(output_path),
            "--fail-on-gate",
        ]
    )

    assert exit_code == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["quality_gate"]["passed"] is False


def test_main_returns_zero_for_quality_pass(tmp_path: Path) -> None:
    entry = _entry()
    corpus_path = tmp_path / "corpus.json"
    policy_path = tmp_path / "policy.json"
    corpus_path.write_text(json.dumps({"entries": [entry]}, ensure_ascii=False), encoding="utf-8")
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")

    exit_code = benchmark.main(
        [
            "current",
            "--corpus-json",
            str(corpus_path),
            "--policy",
            str(policy_path),
            "--fail-on-gate",
        ]
    )

    assert exit_code == 0
