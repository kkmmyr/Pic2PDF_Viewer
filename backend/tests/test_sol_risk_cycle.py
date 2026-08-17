from __future__ import annotations

import hashlib

import pytest

from services.novel_db.sol_risk_cycle import (
    apply_single_claim_repair,
    candidate_sha256,
    validate_claim_set,
    verify_independent_review,
)


def _candidate() -> dict:
    sentences = [f"E{index:02}の監査対象文。" for index in range(1, 42)]
    sentences[17] = "仁耀は承諾して解放され、茉莉花へ白楼国の未来を託して去った。"
    detailed = "".join(sentences)
    claims = []
    cursor = 0
    artifact_sha = hashlib.sha256(detailed.encode("utf-8")).hexdigest()
    for index, sentence in enumerate(sentences, start=1):
        start = detailed.index(sentence, cursor)
        end = start + len(sentence)
        cursor = end
        claims.append(
            {
                "claim_id": f"E{index:02}",
                "artifact": "detailed_summary",
                "start": start,
                "end": end,
                "artifact_text": sentence,
                "artifact_sha256": artifact_sha,
                "sentence_sha256": hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
                "categories": ["test"],
            }
        )
    candidate = {
        "schema_version": "sol-risk-candidate-v1",
        "source_sha256": "a" * 64,
        "extractor_version": "risk-exact-v1",
        "extractor_sha256": "b" * 64,
        "artifacts": {"detailed_summary": detailed},
        "claims": claims,
    }
    candidate["candidate_sha256"] = candidate_sha256(candidate)
    return candidate


def test_apply_repair_changes_only_e18_and_rebuilds_all_claim_hashes() -> None:
    candidate = _candidate()
    repaired = apply_single_claim_repair(
        candidate,
        {
            "base_candidate_sha256": candidate["candidate_sha256"],
            "claim_id": "E18",
            "old_sentence_sha256": candidate["claims"][17]["sentence_sha256"],
            "replacement_text": (
                "仁耀は承諾して解放され、茉莉花に「あとは頼んだ」と告げ、託した対象を限定しないまま去った。"
            ),
            "repair_run_id": "repair-e18-r1",
        },
    )

    assert validate_claim_set(repaired, expected_count=41)["claim_count"] == 41
    assert repaired["claims"][17]["artifact_text"].endswith("限定しないまま去った。")
    assert [claim["artifact_text"] for claim in repaired["claims"][:17]] == [
        claim["artifact_text"] for claim in candidate["claims"][:17]
    ]
    assert [claim["artifact_text"] for claim in repaired["claims"][18:]] == [
        claim["artifact_text"] for claim in candidate["claims"][18:]
    ]
    assert repaired["parent_candidate_sha256"] == candidate["candidate_sha256"]
    assert repaired["candidate_sha256"] != candidate["candidate_sha256"]


def test_apply_repair_rejects_non_e18_or_stale_base() -> None:
    candidate = _candidate()
    repair = {
        "base_candidate_sha256": candidate["candidate_sha256"],
        "claim_id": "E17",
        "old_sentence_sha256": candidate["claims"][16]["sentence_sha256"],
        "replacement_text": "変更。",
        "repair_run_id": "repair-r1",
    }
    with pytest.raises(ValueError, match="E18"):
        apply_single_claim_repair(candidate, repair)

    repair["claim_id"] = "E18"
    repair["base_candidate_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="base candidate"):
        apply_single_claim_repair(candidate, repair)


def test_independent_review_requires_fresh_run_and_all_41_supported() -> None:
    candidate = _candidate()
    candidate["repair_run_id"] = "repair-e18-r1"
    candidate["candidate_sha256"] = candidate_sha256(candidate)
    review = {
        "schema_version": "sol-risk-review-v1",
        "source_sha256": candidate["source_sha256"],
        "candidate_sha256": candidate["candidate_sha256"],
        "extractor_version": candidate["extractor_version"],
        "extractor_sha256": candidate["extractor_sha256"],
        "review_run_id": "review-fresh-r1",
        "results": [
            {
                "claim_id": claim["claim_id"],
                "sentence_sha256": claim["sentence_sha256"],
                "verdict": "supported",
                "severity": "none",
            }
            for claim in candidate["claims"]
        ],
    }

    result = verify_independent_review(candidate, review, expected_count=41)
    assert result["passed"] is True
    assert result["supported_count"] == 41

    review["review_run_id"] = "repair-e18-r1"
    with pytest.raises(ValueError, match="fresh run"):
        verify_independent_review(candidate, review, expected_count=41)

    review["review_run_id"] = "review-fresh-r2"
    review["results"][17]["verdict"] = "unsupported"
    review["results"][17]["severity"] = "major"
    with pytest.raises(ValueError, match="not fully supported"):
        verify_independent_review(candidate, review, expected_count=41)
