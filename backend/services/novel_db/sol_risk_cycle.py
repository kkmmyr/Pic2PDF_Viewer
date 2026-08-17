"""Deterministic E18 repair scope and exact-sentence review verification."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

CANDIDATE_SCHEMA_VERSION = "sol-risk-candidate-v1"
REVIEW_SCHEMA_VERSION = "sol-risk-review-v1"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def candidate_sha256(candidate: Mapping[str, Any]) -> str:
    content = {key: value for key, value in candidate.items() if key != "candidate_sha256"}
    encoded = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_candidate_header(candidate: Mapping[str, Any]) -> str:
    if candidate.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        raise ValueError("unsupported Sol risk candidate schema")
    for field in ("source_sha256", "extractor_sha256"):
        if len(str(candidate.get(field) or "")) != 64:
            raise ValueError(f"candidate {field} is invalid")
    if not str(candidate.get("extractor_version") or ""):
        raise ValueError("candidate extractor_version is required")
    expected_candidate_sha = candidate_sha256(candidate)
    if candidate.get("candidate_sha256") != expected_candidate_sha:
        raise ValueError("candidate digest mismatch")
    return expected_candidate_sha


def _validate_claim(
    claim: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    seen_ids: set[str],
    previous_end: dict[str, int],
) -> None:
    claim_id = str(claim.get("claim_id") or "")
    if not claim_id or claim_id in seen_ids:
        raise ValueError(f"duplicate or empty claim ID: {claim_id}")
    seen_ids.add(claim_id)
    artifact_name = str(claim.get("artifact") or "")
    artifact = artifacts.get(artifact_name)
    if not isinstance(artifact, str):
        raise ValueError(f"claim artifact is missing: {claim_id}")
    start = int(claim["start"])
    end = int(claim["end"])
    artifact_text = str(claim["artifact_text"])
    if start < previous_end[artifact_name] or end <= start:
        raise ValueError(f"claim offsets overlap or are invalid: {claim_id}")
    if artifact[start:end] != artifact_text:
        raise ValueError(f"claim exact text mismatch: {claim_id}")
    if claim.get("artifact_sha256") != _sha256_text(artifact):
        raise ValueError(f"claim artifact digest mismatch: {claim_id}")
    if claim.get("sentence_sha256") != _sha256_text(artifact_text):
        raise ValueError(f"claim sentence digest mismatch: {claim_id}")
    previous_end[artifact_name] = end


def validate_claim_set(candidate: Mapping[str, Any], *, expected_count: int = 41) -> dict[str, Any]:
    expected_candidate_sha = _validate_candidate_header(candidate)
    artifacts = candidate.get("artifacts")
    claims = candidate.get("claims")
    if not isinstance(artifacts, Mapping) or not isinstance(claims, list):
        raise ValueError("candidate artifacts and claims are required")
    if len(claims) != expected_count:
        raise ValueError(f"candidate must contain exactly {expected_count} claims")

    seen_ids: set[str] = set()
    previous_end: dict[str, int] = defaultdict(int)
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise ValueError("candidate claim must be an object")
        _validate_claim(claim, artifacts, seen_ids, previous_end)
    return {
        "candidate_sha256": expected_candidate_sha,
        "claim_count": len(claims),
        "artifact_count": len(artifacts),
    }


def _rebuild_claim_locations(candidate: dict[str, Any], replacement_text: str) -> None:
    claims_by_artifact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in candidate["claims"]:
        claim = dict(claim)
        if claim["claim_id"] == "E18":
            claim["artifact_text"] = replacement_text
        claims_by_artifact[str(claim["artifact"])].append(claim)

    rebuilt = []
    for artifact_name, claims in claims_by_artifact.items():
        artifact = str(candidate["artifacts"][artifact_name])
        artifact_sha = _sha256_text(artifact)
        cursor = 0
        for claim in claims:
            artifact_text = str(claim["artifact_text"])
            start = artifact.find(artifact_text, cursor)
            if start < 0:
                raise ValueError(f"repaired claim text is not found: {claim['claim_id']}")
            end = start + len(artifact_text)
            claim.update(
                {
                    "start": start,
                    "end": end,
                    "artifact_sha256": artifact_sha,
                    "sentence_sha256": _sha256_text(artifact_text),
                }
            )
            rebuilt.append(claim)
            cursor = end
    order = {str(claim["claim_id"]): index for index, claim in enumerate(candidate["claims"])}
    rebuilt.sort(key=lambda claim: order[str(claim["claim_id"])])
    candidate["claims"] = rebuilt


def apply_single_claim_repair(
    candidate: Mapping[str, Any],
    repair: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_claim_set(candidate)
    if repair.get("base_candidate_sha256") != validation["candidate_sha256"]:
        raise ValueError("repair base candidate digest mismatch")
    if repair.get("claim_id") != "E18":
        raise ValueError("only the separately approved E18 repair is allowed")
    repair_run_id = str(repair.get("repair_run_id") or "").strip()
    replacement_text = str(repair.get("replacement_text") or "")
    if not repair_run_id or not replacement_text.strip():
        raise ValueError("repair_run_id and replacement_text are required")

    target = next(claim for claim in candidate["claims"] if claim["claim_id"] == "E18")
    if repair.get("old_sentence_sha256") != target["sentence_sha256"]:
        raise ValueError("E18 sentence digest mismatch")
    artifact_name = str(target["artifact"])
    artifact = str(candidate["artifacts"][artifact_name])
    start, end = int(target["start"]), int(target["end"])
    if artifact[start:end] != target["artifact_text"]:
        raise ValueError("E18 exact text no longer matches the candidate")

    repaired = copy.deepcopy(dict(candidate))
    repaired["artifacts"][artifact_name] = artifact[:start] + replacement_text + artifact[end:]
    repaired["parent_candidate_sha256"] = validation["candidate_sha256"]
    repaired["repair_run_id"] = repair_run_id
    repaired.pop("candidate_sha256", None)
    _rebuild_claim_locations(repaired, replacement_text)
    repaired["candidate_sha256"] = candidate_sha256(repaired)
    validate_claim_set(repaired)
    return repaired


def verify_independent_review(
    candidate: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    expected_count: int = 41,
) -> dict[str, Any]:
    validation = validate_claim_set(candidate, expected_count=expected_count)
    _validate_review_identity(candidate, review)
    review_run_id = str(review.get("review_run_id") or "").strip()
    if not review_run_id or review_run_id == candidate.get("repair_run_id"):
        raise ValueError("independent review must use a fresh run")
    results = review.get("results")
    if not isinstance(results, list) or len(results) != expected_count:
        raise ValueError(f"independent review must contain exactly {expected_count} results")
    results_by_id = {str(result.get("claim_id")): result for result in results if isinstance(result, Mapping)}
    if len(results_by_id) != expected_count:
        raise ValueError("independent review contains duplicate or missing claim IDs")

    failures = []
    for claim in candidate["claims"]:
        claim_id = str(claim["claim_id"])
        result = results_by_id.get(claim_id)
        if result is None or result.get("sentence_sha256") != claim["sentence_sha256"]:
            raise ValueError(f"independent review claim digest mismatch: {claim_id}")
        if result.get("verdict") != "supported" or result.get("severity") not in {"none", None}:
            failures.append(claim_id)
    if failures:
        raise ValueError(f"independent review is not fully supported: {failures}")
    return {
        "passed": True,
        "candidate_sha256": validation["candidate_sha256"],
        "review_run_id": review_run_id,
        "supported_count": expected_count,
    }


def _validate_review_identity(candidate: Mapping[str, Any], review: Mapping[str, Any]) -> None:
    if review.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ValueError("unsupported Sol risk review schema")
    identity_fields = (
        "source_sha256",
        "candidate_sha256",
        "extractor_version",
        "extractor_sha256",
    )
    mismatches = [field for field in identity_fields if review.get(field) != candidate.get(field)]
    if mismatches:
        raise ValueError(f"independent review {mismatches[0]} mismatch")
