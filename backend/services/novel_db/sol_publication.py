"""Fail-closed validation for Sol publication artifacts and their reviews."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .sol_fact_graph import load_pages, validate_candidate

PUBLICATION_SCHEMA_VERSION = "sol-publication-v1"
PUBLICATION_REVIEW_SCHEMA_VERSION = "sol-publication-review-v1"
_VERDICTS = {"supported", "contradicted", "unsupported"}
_SENTENCE_RE = re.compile(r"[^。！？\n]+[。！？]?")


def artifact_sentences(publication: Mapping[str, Any]) -> dict[str, list[str]]:
    artifacts: dict[str, list[str]] = {}
    for field in ("detailed_summary", "catalog_summary"):
        value = publication.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
        artifacts[field] = [match.group(0).strip() for match in _SENTENCE_RE.finditer(value) if match.group(0).strip()]
    characters = publication.get("characters")
    if not isinstance(characters, list) or not characters:
        raise ValueError("characters are required")
    seen_names: set[str] = set()
    for character in characters:
        if not isinstance(character, Mapping):
            raise ValueError("character must be an object")
        name = character.get("name")
        description = character.get("description")
        if not isinstance(name, str) or not name.strip() or name in seen_names:
            raise ValueError(f"duplicate or empty character name: {name}")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"character {name} description is required")
        seen_names.add(name)
        artifacts[f"character:{name}"] = [
            match.group(0).strip() for match in _SENTENCE_RE.finditer(description) if match.group(0).strip()
        ]
    return artifacts


def _validate_publication_header(
    publication: Mapping[str, Any],
    candidate_result: Mapping[str, Any],
    *,
    expected_source_sha256: str,
) -> tuple[str, str]:
    if publication.get("schema_version") != PUBLICATION_SCHEMA_VERSION:
        raise ValueError("unsupported Sol publication schema")
    if publication.get("source_sha256") != expected_source_sha256:
        raise ValueError("publication source digest mismatch")
    if publication.get("candidate_sha256") != candidate_result["candidate_sha256"]:
        raise ValueError("publication candidate digest mismatch")
    detailed = publication.get("detailed_summary")
    catalog = publication.get("catalog_summary")
    if not isinstance(detailed, str) or not 800 <= len(detailed) <= 3000:
        raise ValueError("detailed_summary must be 800-3000 characters")
    if not isinstance(catalog, str) or not 400 <= len(catalog) <= 700:
        raise ValueError("catalog_summary must be 400-700 characters")
    return detailed, catalog


def _validate_character_references(
    characters: Any,
    fact_ids: set[str],
) -> None:
    for character in characters:
        references = character.get("fact_ids")
        if (
            not isinstance(references, list)
            or not references
            or any(not isinstance(value, str) for value in references)
        ):
            raise ValueError(f"character {character['name']} fact_ids are required")
        unknown = set(references) - fact_ids
        if unknown:
            raise ValueError(f"character {character['name']} references unknown facts: {sorted(unknown)}")


def _validate_claim(
    claim: Any,
    seen_claim_ids: set[str],
    artifacts: Mapping[str, list[str]],
    fact_ids: set[str],
    actual: Counter[tuple[str, str]],
) -> None:
    if not isinstance(claim, Mapping):
        raise ValueError("publication claim must be an object")
    claim_id = claim.get("claim_id")
    artifact = claim.get("artifact")
    text = claim.get("text")
    references = claim.get("fact_ids")
    if not isinstance(claim_id, str) or not claim_id or claim_id in seen_claim_ids:
        raise ValueError(f"duplicate or empty claim ID: {claim_id}")
    seen_claim_ids.add(claim_id)
    if not isinstance(artifact, str) or artifact not in artifacts:
        raise ValueError(f"claim {claim_id} has an unknown artifact")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"claim {claim_id} text is required")
    if not isinstance(references, list) or not references or any(not isinstance(value, str) for value in references):
        raise ValueError(f"claim {claim_id} fact_ids are required")
    unknown = set(references) - fact_ids
    if unknown:
        raise ValueError(f"claim {claim_id} references unknown facts: {sorted(unknown)}")
    actual[(artifact, text)] += 1


def _validate_claims(
    claims: Any,
    artifacts: Mapping[str, list[str]],
    fact_ids: set[str],
) -> Counter[tuple[str, str]]:
    if not isinstance(claims, list) or not claims:
        raise ValueError("publication claims are required")
    seen_claim_ids: set[str] = set()
    actual: Counter[tuple[str, str]] = Counter()
    for claim in claims:
        _validate_claim(claim, seen_claim_ids, artifacts, fact_ids, actual)
    return actual


def _validate_review_header(
    review: Mapping[str, Any],
    publication_result: Mapping[str, Any],
    *,
    expected_source_sha256: str,
    writing_run_id: str,
) -> str:
    if review.get("schema_version") != PUBLICATION_REVIEW_SCHEMA_VERSION:
        raise ValueError("unsupported Sol publication review schema")
    if review.get("source_sha256") != expected_source_sha256:
        raise ValueError("publication review source digest mismatch")
    if review.get("candidate_sha256") != publication_result["candidate_sha256"]:
        raise ValueError("publication review candidate digest mismatch")
    review_run_id = review.get("review_run_id")
    if not isinstance(review_run_id, str) or not review_run_id or review_run_id == writing_run_id:
        raise ValueError("publication review must use a fresh run")
    return review_run_id


def _index_review_results(
    results: Any,
    claims: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(results, list) or len(results) != len(claims):
        raise ValueError("publication review result count mismatch")
    by_id = {str(item.get("claim_id")): item for item in results if isinstance(item, Mapping)}
    expected_ids = {str(claim["claim_id"]) for claim in claims}
    if set(by_id) != expected_ids or len(by_id) != len(results):
        raise ValueError("publication review contains duplicate, missing, or extra IDs")
    return by_id


def _validate_review_evidence(
    claim_id: str,
    evidence: Any,
    pages: Mapping[int, str],
) -> None:
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"publication review {claim_id} must have evidence")
    for item in evidence:
        if not isinstance(item, Mapping):
            raise ValueError(f"publication review {claim_id} evidence must be an object")
        page_no = item.get("page_no")
        quote = item.get("quote")
        if isinstance(page_no, bool) or not isinstance(page_no, int) or page_no not in pages:
            raise ValueError(f"publication review {claim_id} has an invalid evidence page")
        if not isinstance(quote, str) or not 20 <= len(quote) <= 120 or quote not in pages[page_no]:
            raise ValueError(f"publication review {claim_id} evidence is not exact source text")


def _validate_review_claim(
    claim_id: str,
    result: Mapping[str, Any],
    pages: Mapping[int, str],
    failures: list[str],
) -> None:
    verdict = result.get("verdict")
    if verdict not in _VERDICTS:
        raise ValueError(f"publication review {claim_id} verdict is invalid")
    _validate_review_evidence(claim_id, result.get("evidence"), pages)
    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"publication review {claim_id} reason is required")
    if verdict != "supported":
        failures.append(claim_id)


def validate_publication(
    publication: Mapping[str, Any],
    candidate: Mapping[str, Any],
    page_records: Sequence[Mapping[str, Any]],
    *,
    expected_source_sha256: str,
) -> dict[str, Any]:
    candidate_result = validate_candidate(
        candidate,
        page_records,
        expected_source_sha256=expected_source_sha256,
    )
    detailed, catalog = _validate_publication_header(
        publication,
        candidate_result,
        expected_source_sha256=expected_source_sha256,
    )

    fact_ids = {str(fact["fact_id"]) for fact in candidate["facts"]}
    artifacts = artifact_sentences(publication)
    characters = publication["characters"]
    _validate_character_references(characters, fact_ids)
    claims = publication.get("claims")
    if not isinstance(claims, list):
        raise ValueError("publication claims are required")
    actual = _validate_claims(claims, artifacts, fact_ids)

    expected = Counter((artifact, sentence) for artifact, sentences in artifacts.items() for sentence in sentences)
    if actual != expected:
        missing = list((expected - actual).elements())
        extra = list((actual - expected).elements())
        raise ValueError(f"publication sentence coverage mismatch: missing={missing}, extra={extra}")
    unresolved = publication.get("unresolved")
    if not isinstance(unresolved, list) or any(not isinstance(value, str) or not value.strip() for value in unresolved):
        raise ValueError("unresolved must be a string array")
    return {
        "passed": True,
        "claim_count": len(claims),
        "character_count": len(characters),
        "detailed_chars": len(detailed),
        "catalog_chars": len(catalog),
        "candidate_sha256": candidate_result["candidate_sha256"],
    }


def verify_publication_review(
    publication: Mapping[str, Any],
    candidate: Mapping[str, Any],
    review: Mapping[str, Any],
    page_records: Sequence[Mapping[str, Any]],
    *,
    expected_source_sha256: str,
    writing_run_id: str,
) -> dict[str, Any]:
    publication_result = validate_publication(
        publication,
        candidate,
        page_records,
        expected_source_sha256=expected_source_sha256,
    )
    pages = load_pages(page_records)
    review_run_id = _validate_review_header(
        review,
        publication_result,
        expected_source_sha256=expected_source_sha256,
        writing_run_id=writing_run_id,
    )
    results = review.get("results")
    if not isinstance(results, list):
        raise ValueError("publication review result count mismatch")
    claims = publication["claims"]
    by_id = _index_review_results(results, claims)
    failures: list[str] = []
    for claim_id in sorted(by_id):
        _validate_review_claim(claim_id, by_id[claim_id], pages, failures)
    if failures:
        raise ValueError(f"publication review is not fully supported: {failures}")
    return {
        "passed": True,
        "review_run_id": review_run_id,
        "supported_count": len(results),
    }
