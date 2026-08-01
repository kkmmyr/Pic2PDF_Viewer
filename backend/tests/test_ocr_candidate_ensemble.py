from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "ensemble_ocr_candidates.py"
_SPEC = importlib.util.spec_from_file_location("ensemble_ocr_candidates", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
ensemble = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ensemble)


def test_align_to_pivot_preserves_insertions_and_deletions() -> None:
    aligned, gaps = ensemble.align_to_pivot("ABCDE", "ABxCDE!")

    assert aligned == list("ABCDE")
    assert gaps == ["", "", "x", "", "", "!"]

    aligned, gaps = ensemble.align_to_pivot("ABCDE", "ABDE")
    assert aligned == ["A", "B", None, "D", "E"]
    assert gaps == ["", "", "", "", "", ""]


def test_character_consensus_uses_supported_change_and_gap() -> None:
    text, decision = ensemble.character_consensus(
        [
            ("a", "ABCDE"),
            ("b", "ABxCYZ"),
            ("c", "ABxCYZ"),
            ("d", "ABxCYE"),
        ]
    )

    assert text == "ABxCYZ"
    assert decision["candidate_count"] == 4


def test_character_consensus_requires_three_votes_to_delete() -> None:
    text, _ = ensemble.character_consensus([("a", "ABCDE"), ("b", "ABDE"), ("c", "ABDE"), ("d", "ABCDE")])

    assert text == "ABCDE"


def test_ensemble_reports_scopes_to_first_report() -> None:
    entry = {
        "id": 1,
        "run_id": 10,
        "page_no": 2,
        "page_type": "narrative",
        "layout_type": "normal_prose",
        "reference_text": "ABC",
        "image_sha256": "sha",
        "state": "verified",
    }
    unused = {**entry, "id": 2, "image_sha256": "unused"}
    reports = [
        {
            "engine": engine,
            "pages": [{"entry_id": 1, "image_sha256": "sha", "hypothesis": "ABC"}],
        }
        for engine in ("a", "b", "c")
    ]

    result = ensemble.ensemble_reports({"entries": [entry, unused]}, reports)

    assert [page["entry_id"] for page in result["pages"]] == [1]
