"""接続や表示形式に依存しないページ単位のRRF統合。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class RankedPage:
    book_name: str
    page_no: int
    score: float = 0.0
    raw_snippet: str | None = None
    vector_text: str | None = None


def rank_pages(
    lexical: Sequence[tuple],
    vector: Sequence[tuple],
    *,
    top: int,
    k_rrf: int,
    max_per_book: int | None,
) -> list[RankedPage]:
    pages: dict[tuple[str, int], RankedPage] = {}
    for rank, (book_name, page_no, raw_snippet, _score) in enumerate(lexical):
        entry = pages.setdefault((book_name, page_no), RankedPage(book_name, page_no))
        entry.score += 1.0 / (k_rrf + rank + 1)
        if entry.raw_snippet is None:
            entry.raw_snippet = raw_snippet

    for rank, (book_name, page_no, text, _distance) in enumerate(vector):
        entry = pages.setdefault((book_name, page_no), RankedPage(book_name, page_no))
        entry.score += 1.0 / (k_rrf + rank + 1)
        if entry.vector_text is None:
            entry.vector_text = text

    # Stable sort preserves lexical-then-vector first-seen order on equal scores.
    ranked = sorted(pages.values(), key=lambda page: -page.score)
    if max_per_book is not None and max_per_book > 0:
        per_book: dict[str, int] = {}
        filtered: list[RankedPage] = []
        for page in ranked:
            if per_book.get(page.book_name, 0) >= max_per_book:
                continue
            per_book[page.book_name] = per_book.get(page.book_name, 0) + 1
            filtered.append(page)
            if len(filtered) >= top:
                break
        return filtered
    return ranked[:top]
