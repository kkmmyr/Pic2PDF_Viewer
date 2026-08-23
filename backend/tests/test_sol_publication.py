"""Tests for grounded Sol publication and independent review gates."""

from __future__ import annotations

import copy

import pytest

from services.novel_db.sol_fact_graph import seal_candidate
from services.novel_db.sol_job_package import source_sha256
from services.novel_db.sol_publication import artifact_sentences, validate_publication, verify_publication_review

_QUOTE = "茉莉花は朝議で調査結果を報告し、珀陽はその提案を正式に承認した。"
_PAGES = [{"page_no": 8, "full_text": f"前文。{_QUOTE}後文。", "char_count": len(f"前文。{_QUOTE}後文。")}]
_SOURCE_SHA = source_sha256(_PAGES)
_RAW_CANDIDATE = {
    "schema_version": "sol-fact-graph-v1",
    "source_sha256": _SOURCE_SHA,
    "facts": [
        {
            "fact_id": "F001",
            "subject": "茉莉花",
            "action": "調査結果を報告した",
            "object": "朝議への提案",
            "actors": [
                {"name": "茉莉花", "role": "subject"},
                {"name": "珀陽", "role": "command_approver"},
            ],
            "temporality": "past",
            "certainty": "fact",
            "state_before": "提案は未承認だった",
            "state_after": "提案は承認された",
            "evidence": [{"page_no": 8, "quote": _QUOTE}],
            "related_fact_ids": [],
        }
    ],
}
_CANDIDATE = seal_candidate(_RAW_CANDIDATE, _PAGES, expected_source_sha256=_SOURCE_SHA)


def _publication() -> dict:
    detailed_sentence = "茉莉花は朝議で調査結果を報告し、珀陽の正式な承認を得て提案を前進させた。"
    catalog_sentence = "茉莉花が朝議で調査結果を報告し、珀陽が提案を正式に承認するまでを描く。"
    character_sentence = "朝議で調査結果を報告し、提案を前進させた人物。"
    publication = {
        "schema_version": "sol-publication-v1",
        "source_sha256": _SOURCE_SHA,
        "candidate_sha256": _CANDIDATE["candidate_sha256"],
        "detailed_summary": detailed_sentence * 24,
        "catalog_summary": catalog_sentence * 13,
        "characters": [
            {"name": "茉莉花", "description": character_sentence, "fact_ids": ["F001"]},
        ],
        "claims": [],
        "unresolved": [],
    }
    claim_number = 0
    for artifact, sentences in artifact_sentences(publication).items():
        for sentence in sentences:
            claim_number += 1
            publication["claims"].append(
                {
                    "claim_id": f"C{claim_number:03d}",
                    "artifact": artifact,
                    "text": sentence,
                    "fact_ids": ["F001"],
                }
            )
    return publication


def test_validate_publication_requires_complete_sentence_coverage() -> None:
    publication = _publication()
    result = validate_publication(
        publication,
        _CANDIDATE,
        _PAGES,
        expected_source_sha256=_SOURCE_SHA,
    )
    assert result["passed"] is True
    assert result["claim_count"] == 38

    publication["claims"].pop()
    with pytest.raises(ValueError, match="sentence coverage mismatch"):
        validate_publication(
            publication,
            _CANDIDATE,
            _PAGES,
            expected_source_sha256=_SOURCE_SHA,
        )


def test_validate_publication_rejects_unknown_fact_reference() -> None:
    publication = _publication()
    publication["claims"][0]["fact_ids"] = ["F999"]
    with pytest.raises(ValueError, match="unknown facts"):
        validate_publication(
            publication,
            _CANDIDATE,
            _PAGES,
            expected_source_sha256=_SOURCE_SHA,
        )


def test_publication_review_requires_fresh_run_and_all_supported() -> None:
    publication = _publication()
    review = {
        "schema_version": "sol-publication-review-v1",
        "source_sha256": _SOURCE_SHA,
        "candidate_sha256": _CANDIDATE["candidate_sha256"],
        "review_run_id": "review-2",
        "results": [
            {
                "claim_id": claim["claim_id"],
                "verdict": "supported",
                "evidence": [{"page_no": 8, "quote": _QUOTE}],
                "reason": "原文が支持する。",
            }
            for claim in publication["claims"]
        ],
    }
    result = verify_publication_review(
        publication,
        _CANDIDATE,
        review,
        _PAGES,
        expected_source_sha256=_SOURCE_SHA,
        writing_run_id="writer-1",
    )
    assert result["supported_count"] == len(publication["claims"])

    failed = copy.deepcopy(review)
    failed["results"][0]["verdict"] = "unsupported"
    with pytest.raises(ValueError, match="not fully supported"):
        verify_publication_review(
            publication,
            _CANDIDATE,
            failed,
            _PAGES,
            expected_source_sha256=_SOURCE_SHA,
            writing_run_id="writer-1",
        )

    review["review_run_id"] = "writer-1"
    with pytest.raises(ValueError, match="fresh run"):
        verify_publication_review(
            publication,
            _CANDIDATE,
            review,
            _PAGES,
            expected_source_sha256=_SOURCE_SHA,
            writing_run_id="writer-1",
        )


def test_publication_review_preserves_invalid_page_contract() -> None:
    publication = _publication()
    review = {
        "schema_version": "sol-publication-review-v1",
        "source_sha256": _SOURCE_SHA,
        "candidate_sha256": _CANDIDATE["candidate_sha256"],
        "review_run_id": "review-2",
        "results": [
            {
                "claim_id": claim["claim_id"],
                "verdict": "supported",
                "evidence": [{"page_no": 999, "quote": _QUOTE}],
                "reason": "原文が支持する。",
            }
            for claim in publication["claims"]
        ],
    }

    with pytest.raises(ValueError, match="invalid evidence page"):
        verify_publication_review(
            publication,
            _CANDIDATE,
            review,
            _PAGES,
            expected_source_sha256=_SOURCE_SHA,
            writing_run_id="writer-1",
        )
