"""要約根拠検査応答の純粋parserとdomain model。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, cast

ClaimVerdict = Literal["supported", "contradicted", "unsupported"]
CoverageVerdict = Literal["pass", "fail"]
SummaryContentType = Literal["detailed", "catalog"]

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？!?])")


class GroundingError(ValueError):
    """要約候補が根拠検査契約を満たさない場合に送出する。"""


@dataclass(frozen=True)
class ClaimAssessment:
    claim_id: int
    text: str
    verdict: ClaimVerdict
    evidence_pages: tuple[int, ...]
    reason: str


@dataclass(frozen=True)
class MissingFact:
    pages: tuple[int, ...]
    fact: str


@dataclass(frozen=True)
class GroundingReport:
    claims: tuple[ClaimAssessment, ...]
    coverage_verdict: CoverageVerdict
    missing_facts: tuple[MissingFact, ...]
    coverage_required: bool = True

    @property
    def passed(self) -> bool:
        return all(claim.verdict == "supported" for claim in self.claims) and (
            not self.coverage_required or (self.coverage_verdict == "pass" and not self.missing_facts)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "coverage_required": self.coverage_required,
            "claims": [asdict(claim) for claim in self.claims],
            "coverage": {
                "verdict": self.coverage_verdict,
                "missing_facts": [asdict(fact) for fact in self.missing_facts],
            },
        }


def split_summary_claims(summary: str) -> list[str]:
    """文章を安定した文単位の主張へ分割する。"""
    claims: list[str] = []
    for paragraph in summary.splitlines():
        value = paragraph.strip()
        if value:
            claims.extend(part.strip() for part in _SENTENCE_BOUNDARY_RE.split(value) if part.strip())
    return claims


def parse_grounding_response(
    response: str,
    *,
    claims: list[str],
    candidate_pages: dict[int, tuple[int, ...]],
    coverage_required: bool = True,
    allowed_evidence_pages: set[int] | None = None,
) -> GroundingReport:
    """検証モデルのJSON契約を正規化し厳密に検証する。"""
    payload = _load_payload(response)
    assessments = _parse_claims(
        payload,
        claims=claims,
        candidate_pages=candidate_pages,
        allowed_evidence_pages=allowed_evidence_pages,
    )
    coverage_verdict, missing_facts = _parse_coverage(payload)
    return GroundingReport(
        claims=tuple(assessments),
        coverage_verdict=coverage_verdict,
        missing_facts=tuple(missing_facts),
        coverage_required=coverage_required,
    )


def _load_payload(response: str) -> dict[str, object]:
    try:
        payload = json.loads(response.strip())
    except json.JSONDecodeError as exc:
        raise GroundingError(f"grounding verifier returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise GroundingError("grounding response root must be an object")
    return payload


def _parse_claims(
    payload: dict[str, object],
    *,
    claims: list[str],
    candidate_pages: dict[int, tuple[int, ...]],
    allowed_evidence_pages: set[int] | None,
) -> list[ClaimAssessment]:
    raw_claims = payload.get("claims")
    if not isinstance(raw_claims, list):
        raise GroundingError("grounding response claims must be an array")
    expected_ids = set(range(1, len(claims) + 1))
    seen_ids: set[int] = set()
    assessments: list[ClaimAssessment] = []
    for item in raw_claims:
        if not isinstance(item, dict):
            raise GroundingError("grounding claim result must be an object")
        claim_id = item.get("id")
        if not isinstance(claim_id, int) or claim_id not in expected_ids or claim_id in seen_ids:
            raise GroundingError(f"invalid or duplicate grounding claim id: {claim_id}")
        seen_ids.add(claim_id)
        assessments.append(
            _parse_claim(
                item,
                claim_id=claim_id,
                claim_text=claims[claim_id - 1],
                candidate_pages=candidate_pages,
                allowed_evidence_pages=allowed_evidence_pages,
            )
        )
    if seen_ids != expected_ids:
        raise GroundingError(f"grounding response omitted claim ids: {sorted(expected_ids - seen_ids)}")
    return sorted(assessments, key=lambda item: item.claim_id)


def _parse_claim(
    item: dict[object, object],
    *,
    claim_id: int,
    claim_text: str,
    candidate_pages: dict[int, tuple[int, ...]],
    allowed_evidence_pages: set[int] | None,
) -> ClaimAssessment:
    verdict = item.get("verdict")
    if verdict not in {"supported", "contradicted", "unsupported"}:
        raise GroundingError(f"invalid grounding verdict for claim {claim_id}: {verdict}")
    evidence_pages = _integer_tuple(item.get("evidence_pages"), label=f"claim {claim_id} evidence_pages")
    allowed = allowed_evidence_pages if allowed_evidence_pages is not None else set(candidate_pages.get(claim_id, ()))
    if set(evidence_pages) - allowed:
        label = "provided evidence pages" if allowed_evidence_pages is not None else "candidates"
        raise GroundingError(f"claim {claim_id} cited a page outside its {label}")
    if verdict == "supported" and not evidence_pages:
        raise GroundingError(f"supported claim {claim_id} has no evidence page")
    reason = item.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise GroundingError(f"claim {claim_id} has no reason")
    return ClaimAssessment(
        claim_id=claim_id,
        text=claim_text,
        verdict=cast(ClaimVerdict, verdict),
        evidence_pages=evidence_pages,
        reason=reason.strip(),
    )


def _parse_coverage(payload: dict[str, object]) -> tuple[CoverageVerdict, list[MissingFact]]:
    raw_coverage = payload.get("coverage")
    if not isinstance(raw_coverage, dict):
        raise GroundingError("grounding response coverage must be an object")
    verdict = raw_coverage.get("verdict")
    if verdict not in {"pass", "fail"}:
        raise GroundingError(f"invalid coverage verdict: {verdict}")
    raw_missing = raw_coverage.get("missing_facts")
    if not isinstance(raw_missing, list):
        raise GroundingError("coverage missing_facts must be an array")
    missing_facts = [_parse_missing_fact(item) for item in raw_missing]
    if verdict == "pass" and missing_facts:
        raise GroundingError("coverage cannot pass with missing facts")
    if verdict == "fail" and not missing_facts:
        raise GroundingError("coverage cannot fail without missing facts")
    return verdict, missing_facts


def _parse_missing_fact(item: object) -> MissingFact:
    if not isinstance(item, dict):
        raise GroundingError("missing fact must be an object")
    pages = _integer_tuple(item.get("pages"), label="missing fact pages")
    fact = item.get("fact")
    if not isinstance(fact, str) or not fact.strip():
        raise GroundingError("missing fact text is required")
    return MissingFact(pages=pages, fact=fact.strip())


def _integer_tuple(value: object, *, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not all(isinstance(item, int) and item > 0 for item in value):
        raise GroundingError(f"{label} must be an array of positive integers")
    return tuple(dict.fromkeys(value))
