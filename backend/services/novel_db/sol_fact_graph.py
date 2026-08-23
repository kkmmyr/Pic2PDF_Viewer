"""Fail-closed validation for action-level Sol facts and independent reviews."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .sol_job_package import source_sha256

FACT_SCHEMA_VERSION = "sol-fact-graph-v1"
REVIEW_SCHEMA_VERSION = "sol-fact-review-v1"
ACTOR_ROLES = {
    "subject",
    "tactical_planner",
    "command_approver",
    "physical_actor",
    "target",
    "witness",
    "decision_maker",
}
TEMPORALITIES = {"past", "current", "future", "conditional", "unknown"}
CERTAINTIES = {"fact", "inference", "unknown"}
VERDICTS = {"supported", "contradicted", "unsupported"}
_FACT_ID_RE = re.compile(r"^F(\d+)$")


def _sha256_json(value: Mapping[str, Any], *, exclude: str | None = None) -> str:
    content = {key: item for key, item in value.items() if key != exclude}
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def candidate_sha256(candidate: Mapping[str, Any]) -> str:
    return _sha256_json(candidate, exclude="candidate_sha256")


def seal_candidate(
    candidate: Mapping[str, Any],
    page_records: Sequence[Mapping[str, Any]],
    *,
    expected_source_sha256: str,
) -> dict[str, Any]:
    sealed = normalize_fact_references(candidate)
    sealed.pop("candidate_sha256", None)
    sealed["candidate_sha256"] = candidate_sha256(sealed)
    validate_candidate(sealed, page_records, expected_source_sha256=expected_source_sha256)
    return sealed


def normalize_fact_references(candidate: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(candidate))
    facts = normalized.get("facts")
    if not isinstance(facts, list):
        return normalized
    ids = {str(fact.get("fact_id")) for fact in facts if isinstance(fact, Mapping)}
    numeric_ids: dict[int, list[str]] = {}
    for fact_id in ids:
        match = _FACT_ID_RE.fullmatch(fact_id)
        if match:
            numeric_ids.setdefault(int(match.group(1)), []).append(fact_id)
    for fact in facts:
        if not isinstance(fact, dict) or not isinstance(fact.get("related_fact_ids"), list):
            continue
        repaired: list[Any] = []
        for reference in fact["related_fact_ids"]:
            if reference in ids or not isinstance(reference, str):
                repaired.append(reference)
                continue
            match = _FACT_ID_RE.fullmatch(reference)
            candidates = numeric_ids.get(int(match.group(1)), []) if match else []
            repaired.append(candidates[0] if len(candidates) == 1 else reference)
        fact["related_fact_ids"] = repaired
    return normalized


def apply_quote_repair(
    original: Mapping[str, Any],
    repair: Mapping[str, Any],
    allowed_evidence: Sequence[tuple[str, int]],
    page_records: Sequence[Mapping[str, Any]],
    *,
    expected_source_sha256: str,
) -> dict[str, Any]:
    if not allowed_evidence or len(set(allowed_evidence)) != len(allowed_evidence):
        raise ValueError("allowed quote repairs must be non-empty and unique")
    if repair.get("schema_version") != "sol-fact-quote-repair-v1":
        raise ValueError("unsupported quote repair schema")
    if repair.get("source_sha256") != expected_source_sha256:
        raise ValueError("quote repair source digest mismatch")
    repairs = repair.get("repairs")
    if not isinstance(repairs, list):
        raise ValueError("quote repairs must be an array")
    replacement_by_key: dict[tuple[str, int], str] = {}
    for item in repairs:
        if not isinstance(item, Mapping):
            raise ValueError("quote repair item must be an object")
        fact_id = item.get("fact_id")
        evidence_index = item.get("evidence_index")
        quote = item.get("quote")
        if (
            not isinstance(fact_id, str)
            or isinstance(evidence_index, bool)
            or not isinstance(evidence_index, int)
            or not isinstance(quote, str)
        ):
            raise ValueError("quote repair item has invalid fields")
        key = (fact_id, evidence_index)
        if key in replacement_by_key:
            raise ValueError(f"duplicate quote repair: {fact_id}:{evidence_index}")
        replacement_by_key[key] = quote
    if set(replacement_by_key) != set(allowed_evidence):
        raise ValueError("quote repair does not exactly match the allowlist")

    updated = copy.deepcopy(dict(original))
    updated.pop("candidate_sha256", None)
    updated_facts = updated.get("facts")
    if not isinstance(updated_facts, list):
        raise ValueError("quote repair fact graph is invalid")
    updated_by_id = {str(fact.get("fact_id")): fact for fact in updated_facts if isinstance(fact, dict)}
    if len(updated_by_id) != len(updated_facts):
        raise ValueError("quote repair fact graph has duplicate or invalid facts")
    for fact_id, evidence_index in allowed_evidence:
        if fact_id not in updated_by_id:
            raise ValueError(f"quote repair references unknown fact: {fact_id}")
        evidence = updated_by_id[fact_id].get("evidence")
        if (
            not isinstance(evidence, list)
            or not 0 <= evidence_index < len(evidence)
        ):
            raise ValueError(f"quote repair evidence index is invalid: {fact_id}:{evidence_index}")
        evidence_item = evidence[evidence_index]
        if not isinstance(evidence_item, dict):
            raise ValueError(f"quote repair evidence is invalid: {fact_id}:{evidence_index}")
        evidence_item["quote"] = replacement_by_key[(fact_id, evidence_index)]
    return seal_candidate(updated, page_records, expected_source_sha256=expected_source_sha256)


def load_pages(records: Sequence[Mapping[str, Any]]) -> dict[int, str]:
    pages: dict[int, str] = {}
    normalized: list[dict[str, Any]] = []
    for record in records:
        page_no = record.get("page_no")
        text = record.get("full_text")
        if isinstance(page_no, bool) or not isinstance(page_no, int):
            raise ValueError("page_no must be an integer")
        if page_no in pages:
            raise ValueError(f"duplicate page number: {page_no}")
        if not isinstance(text, str) or not text:
            raise ValueError(f"page {page_no} has no text")
        if record.get("char_count") != len(text):
            raise ValueError(f"page {page_no} char_count mismatch")
        pages[page_no] = text
        normalized.append({"page_no": page_no, "full_text": text, "char_count": len(text)})
    if not pages:
        raise ValueError("pages are empty")
    ordered = sorted(normalized, key=lambda page: int(page["page_no"]))
    if source_sha256(ordered) != source_sha256(normalized):
        raise ValueError("pages must be ordered by page_no")
    return pages


def _validate_evidence(
    evidence: Any,
    pages: Mapping[int, str],
    *,
    owner: str,
) -> None:
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"{owner} must have evidence")
    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            raise ValueError(f"{owner} evidence {index} must be an object")
        page_no = item.get("page_no")
        quote = item.get("quote")
        if isinstance(page_no, bool) or not isinstance(page_no, int) or page_no not in pages:
            raise ValueError(f"{owner} evidence {index} has an invalid page")
        if not isinstance(quote, str) or not 20 <= len(quote) <= 120:
            raise ValueError(f"{owner} evidence {index} quote must be 20-120 characters")
        if quote not in pages[page_no]:
            raise ValueError(f"{owner} evidence {index} quote is not exact source text")


def validate_candidate(
    candidate: Mapping[str, Any],
    page_records: Sequence[Mapping[str, Any]],
    *,
    expected_source_sha256: str,
) -> dict[str, Any]:
    pages = load_pages(page_records)
    if candidate.get("schema_version") != FACT_SCHEMA_VERSION:
        raise ValueError("unsupported Sol fact graph schema")
    if candidate.get("source_sha256") != expected_source_sha256:
        raise ValueError("fact graph source digest mismatch")
    facts = candidate.get("facts")
    if not isinstance(facts, list) or not facts:
        raise ValueError("fact graph must contain facts")
    seen_ids: set[str] = set()
    reference_sets: dict[str, set[str]] = {}
    evidence_count = 0
    for index, fact in enumerate(facts):
        if not isinstance(fact, Mapping):
            raise ValueError(f"fact {index} must be an object")
        fact_id = str(fact.get("fact_id") or "")
        if not fact_id or fact_id in seen_ids:
            raise ValueError(f"duplicate or empty fact ID: {fact_id}")
        seen_ids.add(fact_id)
        for field in ("subject", "action"):
            if not isinstance(fact.get(field), str) or not str(fact[field]).strip():
                raise ValueError(f"fact {fact_id} {field} is required")
        if fact.get("temporality") not in TEMPORALITIES:
            raise ValueError(f"fact {fact_id} temporality is invalid")
        if fact.get("certainty") not in CERTAINTIES:
            raise ValueError(f"fact {fact_id} certainty is invalid")
        actors = fact.get("actors")
        if not isinstance(actors, list) or not actors:
            raise ValueError(f"fact {fact_id} must have actors")
        for actor in actors:
            if (
                not isinstance(actor, Mapping)
                or not isinstance(actor.get("name"), str)
                or not str(actor["name"]).strip()
                or actor.get("role") not in ACTOR_ROLES
            ):
                raise ValueError(f"fact {fact_id} has an invalid actor")
        _validate_evidence(fact.get("evidence"), pages, owner=f"fact {fact_id}")
        evidence_count += len(fact["evidence"])
        related = fact.get("related_fact_ids")
        if not isinstance(related, list) or any(not isinstance(value, str) for value in related):
            raise ValueError(f"fact {fact_id} related_fact_ids is invalid")
        if fact_id in related:
            raise ValueError(f"fact {fact_id} cannot reference itself")
        reference_sets[fact_id] = set(related)
    for fact_id, references in reference_sets.items():
        missing = references - seen_ids
        if missing:
            raise ValueError(f"fact {fact_id} references unknown facts: {sorted(missing)}")
    expected_candidate_sha = candidate_sha256(candidate)
    if candidate.get("candidate_sha256") != expected_candidate_sha:
        raise ValueError("fact graph candidate digest mismatch")
    return {
        "candidate_sha256": expected_candidate_sha,
        "fact_count": len(facts),
        "evidence_count": evidence_count,
        "page_count": len(pages),
    }


def verify_review(
    candidate: Mapping[str, Any],
    review: Mapping[str, Any],
    page_records: Sequence[Mapping[str, Any]],
    *,
    expected_source_sha256: str,
    generation_run_id: str,
) -> dict[str, Any]:
    candidate_result = validate_candidate(candidate, page_records, expected_source_sha256=expected_source_sha256)
    pages = load_pages(page_records)
    if review.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ValueError("unsupported Sol fact review schema")
    if review.get("source_sha256") != expected_source_sha256:
        raise ValueError("fact review source digest mismatch")
    if review.get("candidate_sha256") != candidate_result["candidate_sha256"]:
        raise ValueError("fact review candidate digest mismatch")
    review_run_id = str(review.get("review_run_id") or "")
    if not review_run_id or review_run_id == generation_run_id:
        raise ValueError("fact review must use a fresh run")
    results = review.get("results")
    facts = candidate["facts"]
    if not isinstance(results, list) or len(results) != len(facts):
        raise ValueError("fact review result count mismatch")
    by_id = {str(result.get("fact_id")): result for result in results if isinstance(result, Mapping)}
    expected_ids = {str(fact["fact_id"]) for fact in facts}
    if set(by_id) != expected_ids or len(by_id) != len(results):
        raise ValueError("fact review contains duplicate, missing, or extra IDs")
    failures: list[str] = []
    for fact_id in sorted(expected_ids):
        result = by_id[fact_id]
        if result.get("verdict") not in VERDICTS:
            raise ValueError(f"fact review {fact_id} verdict is invalid")
        _validate_evidence(result.get("evidence"), pages, owner=f"review {fact_id}")
        if result["verdict"] != "supported":
            failures.append(fact_id)
    if failures:
        raise ValueError(f"fact review is not fully supported: {failures}")
    return {
        "passed": True,
        "candidate_sha256": candidate_result["candidate_sha256"],
        "review_run_id": review_run_id,
        "supported_count": len(results),
    }
