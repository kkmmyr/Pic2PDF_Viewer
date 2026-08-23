from __future__ import annotations

import copy

import pytest

from services.novel_db.sol_fact_graph import (
    apply_quote_repair,
    candidate_sha256,
    normalize_fact_references,
    seal_candidate,
    validate_candidate,
    verify_review,
)
from services.novel_db.sol_job_package import source_sha256

_QUOTE_A = "茉莉花は命令を受け、翌朝に都を出発することを決めた。"
_QUOTE_B = "黎天河は仁耀の腕をつかみ、その場で動きを封じた。"
_PAGES = [
    {"page_no": 10, "full_text": f"前文。{_QUOTE_A}後文。", "char_count": 30},
    {"page_no": 11, "full_text": f"前文。{_QUOTE_B}後文。", "char_count": 30},
]
for _page in _PAGES:
    _page["char_count"] = len(_page["full_text"])
_SOURCE_SHA = source_sha256(_PAGES)


def _candidate() -> dict:
    value = {
        "schema_version": "sol-fact-graph-v1",
        "source_sha256": _SOURCE_SHA,
        "facts": [
            {
                "fact_id": "F001",
                "subject": "茉莉花",
                "action": "都を出発すると決める",
                "object": None,
                "actors": [{"name": "茉莉花", "role": "decision_maker"}],
                "temporality": "future",
                "certainty": "fact",
                "state_before": "命令を受けた",
                "state_after": "出発を決定した",
                "evidence": [{"page_no": 10, "quote": _QUOTE_A}],
                "related_fact_ids": ["F002"],
            },
            {
                "fact_id": "F002",
                "subject": "黎天河",
                "action": "仁耀の動きを封じる",
                "object": "仁耀",
                "actors": [
                    {"name": "黎天河", "role": "physical_actor"},
                    {"name": "仁耀", "role": "target"},
                ],
                "temporality": "past",
                "certainty": "fact",
                "state_before": None,
                "state_after": "仁耀は拘束された",
                "evidence": [{"page_no": 11, "quote": _QUOTE_B}],
                "related_fact_ids": ["F001"],
            },
        ],
    }
    value["candidate_sha256"] = candidate_sha256(value)
    return value


def _review(candidate: dict) -> dict:
    return {
        "schema_version": "sol-fact-review-v1",
        "source_sha256": _SOURCE_SHA,
        "candidate_sha256": candidate["candidate_sha256"],
        "review_run_id": "review-run-2",
        "results": [
            {
                "fact_id": "F001",
                "verdict": "supported",
                "evidence": [{"page_no": 10, "quote": _QUOTE_A}],
                "reason": "主体と将来の決定が原文に一致する",
            },
            {
                "fact_id": "F002",
                "verdict": "supported",
                "evidence": [{"page_no": 11, "quote": _QUOTE_B}],
                "reason": "物理的実行者と対象が原文に一致する",
            },
        ],
    }


def test_validate_candidate_requires_exact_source_quotes() -> None:
    candidate = _candidate()
    result = validate_candidate(candidate, _PAGES, expected_source_sha256=_SOURCE_SHA)
    assert result["fact_count"] == 2
    assert result["evidence_count"] == 2

    changed = copy.deepcopy(candidate)
    changed["facts"][0]["evidence"][0]["quote"] = _QUOTE_A.replace("翌朝", "翌日")
    changed["candidate_sha256"] = candidate_sha256(changed)
    with pytest.raises(ValueError, match="exact source text"):
        validate_candidate(changed, _PAGES, expected_source_sha256=_SOURCE_SHA)


def test_seal_candidate_adds_locally_computed_digest() -> None:
    candidate = _candidate()
    candidate.pop("candidate_sha256")

    sealed = seal_candidate(candidate, _PAGES, expected_source_sha256=_SOURCE_SHA)

    assert sealed["candidate_sha256"] == candidate_sha256(sealed)
    assert "candidate_sha256" not in candidate


def test_normalize_fact_references_repairs_only_unique_zero_padding() -> None:
    candidate = _candidate()
    candidate["facts"][0]["related_fact_ids"] = ["F2"]
    normalized = normalize_fact_references(candidate)
    assert normalized["facts"][0]["related_fact_ids"] == ["F002"]
    assert candidate["facts"][0]["related_fact_ids"] == ["F2"]


def test_apply_quote_repair_allows_only_selected_quote() -> None:
    original = _candidate()
    original.pop("candidate_sha256")
    original["facts"][0]["evidence"][0]["quote"] = "茉莉花は翌朝、都を出発することを決めた。"
    repair = {
        "schema_version": "sol-fact-quote-repair-v1",
        "source_sha256": _SOURCE_SHA,
        "repairs": [{"fact_id": "F001", "evidence_index": 0, "quote": _QUOTE_A}],
    }

    sealed = apply_quote_repair(
        original,
        repair,
        [("F001", 0)],
        _PAGES,
        expected_source_sha256=_SOURCE_SHA,
    )
    assert sealed["facts"][0]["evidence"][0]["quote"] == _QUOTE_A

    changed = copy.deepcopy(repair)
    changed["repairs"].append({"fact_id": "F002", "evidence_index": 0, "quote": _QUOTE_B})
    with pytest.raises(ValueError, match="exactly match the allowlist"):
        apply_quote_repair(
            original,
            changed,
            [("F001", 0)],
            _PAGES,
            expected_source_sha256=_SOURCE_SHA,
        )


def test_validate_candidate_rejects_mixed_or_unknown_fact_links() -> None:
    candidate = _candidate()
    candidate["facts"][0]["related_fact_ids"] = ["F999"]
    candidate["candidate_sha256"] = candidate_sha256(candidate)
    with pytest.raises(ValueError, match="unknown facts"):
        validate_candidate(candidate, _PAGES, expected_source_sha256=_SOURCE_SHA)


def test_validate_candidate_rejects_missing_actors_as_contract_error() -> None:
    candidate = _candidate()
    del candidate["facts"][0]["actors"]
    candidate["candidate_sha256"] = candidate_sha256(candidate)

    with pytest.raises(ValueError, match="must have actors"):
        validate_candidate(candidate, _PAGES, expected_source_sha256=_SOURCE_SHA)


def test_verify_review_requires_fresh_complete_supported_review() -> None:
    candidate = _candidate()
    review = _review(candidate)
    result = verify_review(
        candidate,
        review,
        _PAGES,
        expected_source_sha256=_SOURCE_SHA,
        generation_run_id="generation-run-1",
    )
    assert result["passed"] is True
    assert result["supported_count"] == 2

    review["review_run_id"] = "generation-run-1"
    with pytest.raises(ValueError, match="fresh run"):
        verify_review(
            candidate,
            review,
            _PAGES,
            expected_source_sha256=_SOURCE_SHA,
            generation_run_id="generation-run-1",
        )

    review["review_run_id"] = "review-run-3"
    review["results"][1]["verdict"] = "unsupported"
    with pytest.raises(ValueError, match="not fully supported"):
        verify_review(
            candidate,
            review,
            _PAGES,
            expected_source_sha256=_SOURCE_SHA,
            generation_run_id="generation-run-1",
        )
