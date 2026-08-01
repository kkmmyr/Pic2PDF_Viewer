from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

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


def test_supported_proper_noun_correction_requires_exact_candidate_at_same_position() -> None:
    corrected, decision = ensemble.apply_supported_proper_noun_corrections(
        "琳礼",
        [("exact", "琳麗"), ("majority-a", "琳礼"), ("majority-b", "琳礼")],
        ["琳麗"],
    )

    assert corrected == "琳麗"
    assert decision["applied"][0]["exact_support_engines"] == ["exact"]
    assert decision["unresolved"] == []


def test_unsupported_repeated_proper_noun_variant_is_escalated_without_rewrite() -> None:
    corrected, decision = ensemble.apply_supported_proper_noun_corrections(
        "琳麗と琳礼",
        [("a", "琳麗と琳礼"), ("b", "琳麗と琳礼"), ("c", "琳麗と琳礼")],
        ["琳麗"],
    )

    assert corrected == "琳麗と琳礼"
    assert decision["applied"] == []
    assert decision["unresolved"][0]["reason"] == "no_exact_candidate_support"


def test_proper_noun_ledger_rejects_page_specific_ground_truth_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scopes": [
                    {
                        "series": "test",
                        "run_ids": [1],
                        "terms": ["琳麗"],
                        "image_sha256": "forbidden",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported keys"):
        ensemble.load_proper_noun_ledger(path)


def test_ensemble_reports_resolves_only_escalated_pages_with_codex_report() -> None:
    entry = {
        "id": 1,
        "run_id": 10,
        "page_no": 2,
        "page_type": "narrative",
        "layout_type": "normal_prose",
        "reference_text": "ABCDE",
        "image_sha256": "sha",
        "state": "verified",
    }
    hypotheses = ("ABCDE", "XXXXX", "YYYYY")
    reports = [
        {
            "engine": f"engine-{index}",
            "pages": [
                {
                    "entry_id": 1,
                    "image_sha256": "sha",
                    "hypothesis": hypothesis,
                }
            ],
        }
        for index, hypothesis in enumerate(hypotheses)
    ]
    resolution = {
        "engine": "codex-image-qa",
        "pages": [{"entry_id": 1, "image_sha256": "sha", "hypothesis": "ABCDE"}],
    }

    machine = ensemble.ensemble_reports(
        {"entries": [entry]},
        reports,
        escalate_pairwise_distance=0.15,
    )
    result = ensemble.resolve_escalated_report({"entries": [entry]}, machine, resolution)

    assert result["engine"] == "character-consensus-codex-assisted"
    assert result["pages"][0]["hypothesis"] == "ABCDE"
    assert result["qa_escalation"]["entry_ids"] == [1]
    assert result["qa_escalation"]["resolution_engine"] == "codex-image-qa"
