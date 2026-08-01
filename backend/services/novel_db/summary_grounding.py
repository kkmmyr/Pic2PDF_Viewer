"""Bidirectional grounding gate for generated novel summaries."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal

from local_llm import Backend

from ._prompts import GROUNDING_OPTIONS, SUMMARY_GROUNDING_PROMPT
from .fact_checkpoints import FactRecord, validate_and_structure_fact_sheet
from .generation_quality import BookFactSheet
from .search import Scope, hybrid_search

ClaimVerdict = Literal["supported", "contradicted", "unsupported"]
CoverageVerdict = Literal["pass", "fail"]
SummaryContentType = Literal["detailed", "catalog"]

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？!?])")
_NON_CONTENT_RE = re.compile(r"[\s、。！？!?「」『』（）()・：:―—…]+")
_MAX_CLAIMS = 64
_RAG_TOP_PER_CLAIM = 4
_FACT_TOP_PER_CLAIM = 2
_MAX_EVIDENCE_PAGES = 48
_MAX_EVIDENCE_CHARS = 60_000


class GroundingError(ValueError):
    """Raised when a summary cannot pass the grounding gate."""


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
        return (
            all(claim.verdict == "supported" for claim in self.claims)
            and (
                not self.coverage_required
                or (self.coverage_verdict == "pass" and not self.missing_facts)
            )
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


def verify_summary_grounding(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    book_name: str,
    summary: str,
    fact_sheet: BookFactSheet,
    writer_model: str,
    verifier_backend: Backend,
    verifier_model: str,
    content_type: SummaryContentType = "detailed",
    coverage_required: bool = True,
) -> GroundingReport:
    """Verify claims and, for detailed summaries, reverse fact coverage."""
    claims = split_summary_claims(summary)
    if not claims:
        raise GroundingError("summary grounding requires at least one claim")
    if len(claims) > _MAX_CLAIMS:
        raise GroundingError(f"summary grounding claim limit exceeded: {len(claims)}")

    page_rows = conn.execute(
        "SELECT page_no, full_text FROM pages WHERE book_id = ? AND index_eligible = 1 ORDER BY page_no",
        (book_id,),
    ).fetchall()
    page_texts = {int(row[0]): str(row[1] or "") for row in page_rows}
    fact_records = validate_and_structure_fact_sheet(
        fact_sheet,
        allowed_pages=set(page_texts),
    )
    book_records = [record for record in fact_records if record.kind == "book"]

    candidates = _candidate_pages_by_claim(
        conn,
        book_name=book_name,
        claims=claims,
        book_records=book_records,
    )
    selected_pages = _select_evidence_pages(candidates, page_texts)
    selected_set = set(selected_pages)
    candidates = {
        claim_id: tuple(page for page in pages if page in selected_set) for claim_id, pages in candidates.items()
    }

    prompt = SUMMARY_GROUNDING_PROMPT.format(
        book_name=book_name,
        content_type="詳細あらすじ" if content_type == "detailed" else "一覧向け短縮要約",
        coverage_instruction=(
            "- coverageは書籍事実にある主要な発端、対立、転機、結果、人物関係・立場の変化が\n"
            "  要約候補に含まれるかを逆方向に検査する。細かな情景や反復は欠落扱いしない。"
            if coverage_required
            else "- 短縮要約は意図的に情報を絞るため網羅性を欠落判定しない。coverageはpass、missing_factsは空配列にする。"
        ),
        claims=_render_claims(claims, candidates),
        evidence=_render_evidence(selected_pages, page_texts),
        book_facts=fact_sheet.book_facts,
    )
    raw_response = verifier_backend.ask(
        prompt,
        model=verifier_model,
        options=GROUNDING_OPTIONS,
    ).strip()

    try:
        report = parse_grounding_response(
            raw_response,
            claims=claims,
            candidate_pages=candidates,
            coverage_required=coverage_required,
        )
    except GroundingError as exc:
        _save_report(
            conn,
            book_id=book_id,
            summary=summary,
            writer_model=writer_model,
            verifier_model=verifier_model,
            content_type=content_type,
            passed=False,
            payload={"passed": False, "error": str(exc), "raw_response": raw_response},
        )
        raise

    _save_report(
        conn,
        book_id=book_id,
        summary=summary,
        writer_model=writer_model,
        verifier_model=verifier_model,
        content_type=content_type,
        passed=report.passed,
        payload=report.to_dict(),
    )
    if not report.passed:
        failed_claims = [str(claim.claim_id) for claim in report.claims if claim.verdict != "supported"]
        details = []
        if failed_claims:
            details.append(f"failed claims={','.join(failed_claims)}")
        if report.coverage_required and report.missing_facts:
            details.append(f"missing facts={len(report.missing_facts)}")
        raise GroundingError("summary grounding failed: " + "; ".join(details))
    return report


def split_summary_claims(summary: str) -> list[str]:
    """Split prose into stable sentence-level claims without an LLM call."""
    claims: list[str] = []
    for paragraph in summary.splitlines():
        value = paragraph.strip()
        if not value:
            continue
        claims.extend(part.strip() for part in _SENTENCE_BOUNDARY_RE.split(value) if part.strip())
    return claims


def parse_grounding_response(
    response: str,
    *,
    claims: list[str],
    candidate_pages: dict[int, tuple[int, ...]],
    coverage_required: bool = True,
) -> GroundingReport:
    """Parse and strictly validate the verifier's JSON contract."""
    try:
        payload = json.loads(response.strip())
    except json.JSONDecodeError as exc:
        raise GroundingError(f"grounding verifier returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise GroundingError("grounding response root must be an object")

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

        verdict = item.get("verdict")
        if verdict not in {"supported", "contradicted", "unsupported"}:
            raise GroundingError(f"invalid grounding verdict for claim {claim_id}: {verdict}")
        evidence_pages = _integer_tuple(item.get("evidence_pages"), label=f"claim {claim_id} evidence_pages")
        allowed = set(candidate_pages.get(claim_id, ()))
        if set(evidence_pages) - allowed:
            raise GroundingError(f"claim {claim_id} cited a page outside its candidates")
        if verdict == "supported" and not evidence_pages:
            raise GroundingError(f"supported claim {claim_id} has no evidence page")
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise GroundingError(f"claim {claim_id} has no reason")
        assessments.append(
            ClaimAssessment(
                claim_id=claim_id,
                text=claims[claim_id - 1],
                verdict=verdict,
                evidence_pages=evidence_pages,
                reason=reason.strip(),
            )
        )
    if seen_ids != expected_ids:
        missing = sorted(expected_ids - seen_ids)
        raise GroundingError(f"grounding response omitted claim ids: {missing}")

    raw_coverage = payload.get("coverage")
    if not isinstance(raw_coverage, dict):
        raise GroundingError("grounding response coverage must be an object")
    coverage_verdict = raw_coverage.get("verdict")
    if coverage_verdict not in {"pass", "fail"}:
        raise GroundingError(f"invalid coverage verdict: {coverage_verdict}")
    raw_missing = raw_coverage.get("missing_facts")
    if not isinstance(raw_missing, list):
        raise GroundingError("coverage missing_facts must be an array")
    missing_facts: list[MissingFact] = []
    for item in raw_missing:
        if not isinstance(item, dict):
            raise GroundingError("missing fact must be an object")
        pages = _integer_tuple(item.get("pages"), label="missing fact pages")
        fact = item.get("fact")
        if not isinstance(fact, str) or not fact.strip():
            raise GroundingError("missing fact text is required")
        missing_facts.append(MissingFact(pages=pages, fact=fact.strip()))
    if coverage_verdict == "pass" and missing_facts:
        raise GroundingError("coverage cannot pass with missing facts")
    if coverage_verdict == "fail" and not missing_facts:
        raise GroundingError("coverage cannot fail without missing facts")

    assessments.sort(key=lambda item: item.claim_id)
    return GroundingReport(
        claims=tuple(assessments),
        coverage_verdict=coverage_verdict,
        missing_facts=tuple(missing_facts),
        coverage_required=coverage_required,
    )


def _candidate_pages_by_claim(
    conn: sqlite3.Connection,
    *,
    book_name: str,
    claims: list[str],
    book_records: list[FactRecord],
) -> dict[int, tuple[int, ...]]:
    result: dict[int, tuple[int, ...]] = {}
    scope = Scope(type="book", id=book_name)
    for claim_id, claim in enumerate(claims, 1):
        pages: list[int] = []
        hits = hybrid_search(
            conn,
            claim,
            scope,
            top=_RAG_TOP_PER_CLAIM,
            fts_n=12,
            vec_n=12,
        )
        pages.extend(int(hit.page_no) for hit in hits)
        related = sorted(
            book_records,
            key=lambda record: (-_bigram_overlap(claim, record.text), record.pages[0]),
        )
        for record in related[:_FACT_TOP_PER_CLAIM]:
            if _bigram_overlap(claim, record.text) > 0:
                pages.extend(record.pages)
        result[claim_id] = tuple(dict.fromkeys(pages))
    return result


def _select_evidence_pages(
    candidates: dict[int, tuple[int, ...]],
    page_texts: dict[int, str],
) -> list[int]:
    counts = Counter(page for pages in candidates.values() for page in pages if page in page_texts)
    mandatory = list(dict.fromkeys(pages[0] for pages in candidates.values() if pages and pages[0] in page_texts))
    remaining = sorted(
        (page for page in counts if page not in mandatory),
        key=lambda page: (-counts[page], page),
    )
    priority = [*mandatory, *remaining]
    selected: list[int] = []
    used_chars = 0
    for page in priority:
        if len(selected) >= _MAX_EVIDENCE_PAGES:
            break
        page_chars = len(page_texts[page]) + 32
        if selected and used_chars + page_chars > _MAX_EVIDENCE_CHARS:
            continue
        selected.append(page)
        used_chars += page_chars
    return sorted(selected)


def _render_claims(claims: list[str], candidates: dict[int, tuple[int, ...]]) -> str:
    blocks = []
    for claim_id, claim in enumerate(claims, 1):
        pages = ",".join(str(page) for page in candidates.get(claim_id, ())) or "none"
        blocks.append(f"[CLAIM {claim_id}]\n{claim}\ncandidate_pages: {pages}")
    return "\n\n".join(blocks)


def _render_evidence(selected_pages: list[int], page_texts: dict[int, str]) -> str:
    if not selected_pages:
        return "（検索で根拠ページを取得できなかった）"
    return "\n\n".join(f"[page {page}]\n{page_texts[page]}" for page in selected_pages)


def _save_report(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    summary: str,
    writer_model: str,
    verifier_model: str,
    content_type: SummaryContentType,
    passed: bool,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO summary_grounding_reports
            (book_id, content_type, candidate_sha256, writer_model, verifier_model, passed,
             report_json, checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', '+9 hours'))
        """,
        (
            book_id,
            content_type,
            hashlib.sha256(summary.encode("utf-8")).hexdigest(),
            writer_model,
            verifier_model,
            int(passed),
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.commit()


def _bigram_overlap(left: str, right: str) -> int:
    left_units = _bigrams(left)
    right_units = _bigrams(right)
    return len(left_units & right_units)


def _bigrams(value: str) -> set[str]:
    compact = _NON_CONTENT_RE.sub("", value)
    return {compact[index : index + 2] for index in range(max(0, len(compact) - 1))}


def _integer_tuple(value: object, *, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not all(isinstance(item, int) and item > 0 for item in value):
        raise GroundingError(f"{label} must be an array of positive integers")
    return tuple(dict.fromkeys(value))
