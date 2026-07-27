"""OCR page-type classification and index eligibility."""

from __future__ import annotations

import re

PAGE_TYPES = frozenset(
    {
        "unknown",
        "narrative",
        "toc",
        "illustration",
        "colophon_or_ad",
    }
)

_TOC_MARKERS = re.compile(r"目\s*次|もくじ")
_SECTION_MARKERS = re.compile(r"(?:序章|終章|プロローグ|エピローグ|あとがき|第[0-9一二三四五六七八九十百]+[章話節])")
_NARRATIVE_START_MARKERS = re.compile(r"^\s*(?:序章|終章|プロローグ|エピローグ|あとがき)")
_COLOPHON_MARKERS = re.compile(
    r"(?:ISBN|Copyright|©|発行所|発行者|発行日|出版社|編集部|印刷所|"
    r"無断転載|電子書籍|奥付|定価|QRコード|ダウンロード|キャンペーン)"
)


def validate_page_type(page_type: str) -> str:
    if page_type not in PAGE_TYPES:
        allowed = ", ".join(sorted(PAGE_TYPES))
        raise ValueError(f"invalid OCR page type: {page_type}; expected one of {allowed}")
    return page_type


def is_index_eligible(page_type: str) -> bool:
    return validate_page_type(page_type) == "narrative"


def suggest_page_type(
    *,
    page_no: int,
    page_count: int,
    full_text: str | None,
    char_count: int,
) -> str:
    """Return a conservative deterministic suggestion.

    Ambiguous pages deliberately remain ``unknown`` so a reviewer must classify
    them before publication. This prevents headings, ads, and colophons from
    silently entering retrieval indexes.
    """
    text = (full_text or "").strip()
    normalized_count = max(char_count, len(re.sub(r"\s+", "", text)))

    is_front_matter = page_no <= max(12, page_count // 8)
    section_hits = len(_SECTION_MARKERS.findall(text))
    if is_front_matter and (_TOC_MARKERS.search(text) or section_hits >= 3):
        return "toc"
    if normalized_count >= 300 and _NARRATIVE_START_MARKERS.search(text):
        return "narrative"

    colophon_hits = len(_COLOPHON_MARKERS.findall(text))
    is_late_page = page_no >= max(1, page_count - max(8, page_count // 10))
    if colophon_hits >= 2 or (is_late_page and colophon_hits >= 1 and normalized_count < 1200):
        return "colophon_or_ad"

    if normalized_count < 30:
        return "illustration"
    if page_no <= 3 and normalized_count < 200:
        return "illustration"
    if normalized_count >= 300:
        return "narrative"

    return "unknown"
