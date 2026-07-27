"""Run-level guards for OCR content that must not enter the search index."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

_SAMPLE_MARKER_RE = re.compile(r"(?:電子(?:特別)?お試し版|電子(?:特別)?試し読み版|お試し読み版|試し読み版)")
_AFTERWORD_OR_COLOPHON_RE = re.compile(r"(?:あとがき|後書き|奥付|発行所|発行者|発行日|ISBN|Copyright|©)")
_TOC_RE = re.compile(r"(?:目\s*次|もくじ)")
_SECTION_RE = re.compile(r"(?:序章|終章|プロローグ|エピローグ|第[0-9一二三四五六七八九十百]+[章話節])")
_SPACE_RE = re.compile(r"\s+")
_CONTENT_CHAR_RE = re.compile(r"[\w\u3040-\u30ff\u3400-\u9fff]", re.UNICODE)

_MIN_REPEATED_LINE_LENGTH = 10
_MIN_REPEATED_LINE_COUNT = 3
_MIN_LONG_LINE_LENGTH = 40
_MIN_REPEATED_BLOCK_LENGTH = 40
_MIN_REPEATED_BLOCK_COUNT = 2


def detect_sample_boundary(
    pages: Sequence[tuple[int, str]],
    *,
    page_count: int,
) -> int | None:
    """Return the first page of an appended sample book, if confidently detected.

    Front-matter notices are deliberately ignored. A boundary is accepted only
    in the latter half of the book, either by an explicit sample-edition marker
    or by a second table of contents following an afterword/colophon.
    """
    if not pages or page_count <= 0:
        return None

    late_start = max(8, (page_count + 1) // 2)
    late_pages = [(page_no, text or "") for page_no, text in pages if page_no >= late_start]

    for page_no, text in late_pages:
        if _SAMPLE_MARKER_RE.search(_SPACE_RE.sub("", text)):
            return page_no

    terminal_page: int | None = None
    for page_no, text in late_pages:
        compact = _SPACE_RE.sub("", text)
        if terminal_page is not None and page_no > terminal_page:
            section_hits = len(_SECTION_RE.findall(compact))
            if _TOC_RE.search(compact) or section_hits >= 3:
                return page_no
        if terminal_page is None and _AFTERWORD_OR_COLOPHON_RE.search(compact):
            terminal_page = page_no

    return None


def has_suspicious_repetition(text: str | None) -> bool:
    """Return whether OCR text contains implausibly repeated lines or blocks."""
    lines = [_SPACE_RE.sub("", line) for line in (text or "").splitlines()]
    significant = [line for line in lines if len(_CONTENT_CHAR_RE.findall(line)) >= _MIN_REPEATED_LINE_LENGTH]
    line_counts = Counter(significant)
    if any(count >= _MIN_REPEATED_LINE_COUNT for count in line_counts.values()):
        return True
    if any(
        count >= 2 and len(_CONTENT_CHAR_RE.findall(line)) >= _MIN_LONG_LINE_LENGTH
        for line, count in line_counts.items()
    ):
        return True

    blocks = [
        significant[index] + significant[index + 1]
        for index in range(len(significant) - 1)
        if len(_CONTENT_CHAR_RE.findall(significant[index] + significant[index + 1])) >= _MIN_REPEATED_BLOCK_LENGTH
    ]
    return any(count >= _MIN_REPEATED_BLOCK_COUNT for count in Counter(blocks).values())
