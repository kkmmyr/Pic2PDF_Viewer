"""Content-based OCR QA risk annotations."""

from __future__ import annotations

import json
import re

from .connection import with_db
from .ocr_content_guards import has_suspicious_repetition

_HONORIFIC_NAME_RE = re.compile(r"([\u3400-\u9fff々〆ヵヶ]{2,8})(?:さん|様|殿|君|くん|ちゃん)")
_KATAKANA_TERM_RE = re.compile(r"[ァ-ヴー]{4,}")
_WHITESPACE_RE = re.compile(r"\s+")
_LONG_NON_NARRATIVE_TEXT = 300
_CANDIDATE_AUDIT_FLAGS = frozenset({"primary_text_repetition", "external_text_repetition"})
_MANAGED_RISK_FLAGS = frozenset(
    {
        "named_entity_candidate_disagreement",
        "page_type_text_conflict",
        "primary_text_repetition",
        "external_text_repetition",
        "selected_text_repetition",
    }
)


def _candidate_terms(text: str) -> set[str]:
    compact = _WHITESPACE_RE.sub("", text)
    return set(_HONORIFIC_NAME_RE.findall(compact)) | set(_KATAKANA_TERM_RE.findall(compact))


def _has_single_character_variant(primary_terms: set[str], external_terms: set[str]) -> bool:
    primary_only = primary_terms - external_terms
    external_only = external_terms - primary_terms
    return any(
        len(primary) == len(external) and sum(left != right for left, right in zip(primary, external, strict=True)) == 1
        for primary in primary_only
        for external in external_only
    )


def detect_qa_risk_flags(
    *,
    page_type: str,
    full_text: str,
    char_count: int,
    primary_text: str,
    external_text: str,
) -> set[str]:
    """Return review reasons that are independent from OCR pass/fail state."""
    normalized_count = max(char_count, len(_WHITESPACE_RE.sub("", full_text)))
    flags: set[str] = set()
    if page_type != "narrative" and normalized_count >= _LONG_NON_NARRATIVE_TEXT:
        flags.add("page_type_text_conflict")

    if page_type == "narrative" and primary_text.strip() and external_text.strip():
        primary_terms = _candidate_terms(primary_text)
        external_terms = _candidate_terms(external_text)
        if _has_single_character_variant(primary_terms, external_terms):
            flags.add("named_entity_candidate_disagreement")

    if has_suspicious_repetition(primary_text):
        flags.add("primary_text_repetition")
    if has_suspicious_repetition(external_text):
        flags.add("external_text_repetition")
    if has_suspicious_repetition(full_text):
        flags.add("selected_text_repetition")
    return flags


def annotate_run_qa_risks(run_id: int) -> set[int]:
    """Persist risk flags and return pages that require explicit QA."""
    risky_pages: set[int] = set()
    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no, page_type, full_text, char_count, primary_text, external_text, "
            "quality_flags_json, selected_engine, corrected_text "
            "FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (run_id,),
        ).fetchall()
        with conn:
            for row in rows:
                selected_text = {
                    "primary": str(row[4] or row[2] or ""),
                    "external": str(row[5] or ""),
                    "codex": str(row[8] or ""),
                }.get(str(row[7] or "primary"), str(row[2] or ""))
                risk_flags = detect_qa_risk_flags(
                    page_type=str(row[1] or "unknown"),
                    full_text=selected_text,
                    char_count=len(selected_text),
                    primary_text=str(row[4] or row[2] or ""),
                    external_text=str(row[5] or ""),
                )
                page_no = int(row[0])
                quality_flags = set(json.loads(str(row[6] or "[]")))
                if "sample_content_excluded" in quality_flags:
                    risk_flags.discard("page_type_text_conflict")
                updated_flags = sorted((quality_flags - _MANAGED_RISK_FLAGS) | risk_flags)
                if risk_flags - _CANDIDATE_AUDIT_FLAGS:
                    risky_pages.add(page_no)
                if updated_flags == sorted(quality_flags):
                    continue
                conn.execute(
                    "UPDATE ocr_page_results SET quality_flags_json=? WHERE run_id=? AND page_no=?",
                    (json.dumps(updated_flags, ensure_ascii=False), run_id, page_no),
                )
    return risky_pages
