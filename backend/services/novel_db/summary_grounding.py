"""Bidirectional grounding gate for generated novel summaries."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter

from local_llm import Backend

from .fact_checkpoints import FactRecord, validate_and_structure_fact_sheet
from .generation_quality import BookFactSheet
from .grounding_prompts import GROUNDING_OPTIONS, SUMMARY_GROUNDING_PROMPT, SUMMARY_GROUNDING_REPAIR_PROMPT
from .search import Scope, hybrid_search
from .summary_grounding_parser import (
    ClaimAssessment as ClaimAssessment,
)
from .summary_grounding_parser import (
    GroundingError,
    GroundingReport,
    SummaryContentType,
    parse_grounding_response,
    split_summary_claims,
)
from .summary_grounding_parser import (
    MissingFact as MissingFact,
)
from .summary_grounding_repository import save_grounding_report

_NON_CONTENT_RE = re.compile(r"[\s、。！？!?「」『』（）()・：:―—…]+")
_MAX_CLAIMS = 64
_RAG_TOP_PER_CLAIM = 4
_FACT_TOP_PER_CLAIM = 2
_MANDATORY_PAGES_PER_CLAIM = 2
_MAX_EVIDENCE_PAGES = 64
_MAX_EVIDENCE_CHARS = 90_000


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
        error = f"summary grounding claim limit exceeded: {len(claims)}"
        save_grounding_report(
            conn,
            book_id=book_id,
            summary=summary,
            writer_model=writer_model,
            verifier_model=verifier_model,
            content_type=content_type,
            passed=False,
            payload={
                "passed": False,
                "error": error,
                "claim_limit": _MAX_CLAIMS,
                "claims": [{"id": claim_id, "text": claim} for claim_id, claim in enumerate(claims, 1)],
            },
        )
        raise GroundingError(error)

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
    candidates = {
        claim_id: _expand_candidate_neighbors(pages, available_pages=set(page_texts))
        for claim_id, pages in candidates.items()
    }
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

    initial_error: str | None = None
    initial_raw_response: str | None = None
    try:
        report = parse_grounding_response(
            raw_response,
            claims=claims,
            candidate_pages=candidates,
            coverage_required=coverage_required,
            allowed_evidence_pages=selected_set,
        )
    except GroundingError as exc:
        initial_error = str(exc)
        initial_raw_response = raw_response
        repair_prompt = SUMMARY_GROUNDING_REPAIR_PROMPT.format(
            validation_error=initial_error,
            original_prompt=prompt,
            previous_response=initial_raw_response,
        )
        raw_response = verifier_backend.ask(
            repair_prompt,
            model=verifier_model,
            options=GROUNDING_OPTIONS,
        ).strip()
        try:
            report = parse_grounding_response(
                raw_response,
                claims=claims,
                candidate_pages=candidates,
                coverage_required=coverage_required,
                allowed_evidence_pages=selected_set,
            )
        except GroundingError as repair_exc:
            diagnostic_claims = [
                {
                    "id": claim_id,
                    "text": claim,
                    "candidate_pages": list(candidates.get(claim_id, ())),
                }
                for claim_id, claim in enumerate(claims, 1)
            ]
            save_grounding_report(
                conn,
                book_id=book_id,
                summary=summary,
                writer_model=writer_model,
                verifier_model=verifier_model,
                content_type=content_type,
                passed=False,
                payload={
                    "passed": False,
                    "error": str(repair_exc),
                    "initial_error": initial_error,
                    "claims": diagnostic_claims,
                    "selected_evidence_pages": selected_pages,
                    "initial_raw_response": initial_raw_response,
                    "raw_response": raw_response,
                },
            )
            raise

    payload = report.to_dict()
    if initial_error is not None and initial_raw_response is not None:
        payload["repair"] = {
            "attempted": True,
            "initial_error": initial_error,
            "initial_raw_response": initial_raw_response,
        }

    save_grounding_report(
        conn,
        book_id=book_id,
        summary=summary,
        writer_model=writer_model,
        verifier_model=verifier_model,
        content_type=content_type,
        passed=report.passed,
        payload=payload,
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
        related = sorted(
            book_records,
            key=lambda record: (-_bigram_overlap(claim, record.text), record.pages[0]),
        )
        for record in related[:_FACT_TOP_PER_CLAIM]:
            if _bigram_overlap(claim, record.text) > 0:
                pages.extend(record.pages)
        hits = hybrid_search(
            conn,
            claim,
            scope,
            top=_RAG_TOP_PER_CLAIM,
            fts_n=12,
            vec_n=12,
        )
        pages.extend(int(hit.page_no) for hit in hits)
        result[claim_id] = tuple(dict.fromkeys(pages))
    return result


def _select_evidence_pages(
    candidates: dict[int, tuple[int, ...]],
    page_texts: dict[int, str],
) -> list[int]:
    counts = Counter(page for pages in candidates.values() for page in pages if page in page_texts)
    mandatory = list(
        dict.fromkeys(
            page for pages in candidates.values() for page in pages[:_MANDATORY_PAGES_PER_CLAIM] if page in page_texts
        )
    )
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


def _expand_candidate_neighbors(
    pages: tuple[int, ...],
    *,
    available_pages: set[int],
) -> tuple[int, ...]:
    """Keep direct candidates first, then add existing adjacent pages."""
    direct = [page for page in pages if page in available_pages]
    adjacent = [neighbor for page in direct for neighbor in (page - 1, page + 1) if neighbor in available_pages]
    return tuple(dict.fromkeys([*direct, *adjacent]))


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


def _bigram_overlap(left: str, right: str) -> int:
    left_units = _bigrams(left)
    right_units = _bigrams(right)
    return len(left_units & right_units)


def _bigrams(value: str) -> set[str]:
    compact = _NON_CONTENT_RE.sub("", value)
    return {compact[index : index + 2] for index in range(max(0, len(compact) - 1))}
