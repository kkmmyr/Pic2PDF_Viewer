"""検索候補・全文ページをSearchHitへ整形する。検索・DB接続は持たない。"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import quote

from .search_ranking import RankedPage

_MARK_ESCAPED = re.compile(r"&lt;(/?mark)&gt;")


@dataclass
class SearchHit:
    book_name: str
    page_no: int
    snippet: str
    has_highlight: bool
    image_url: str | None
    rrf_score: float
    # ページの主要登場人物（character_extractor が生成、未抽出なら空リスト）
    main_characters: list[str] | None = None

    def __post_init__(self) -> None:
        if self.main_characters is None:
            self.main_characters = []


def _image_url(book_name: str, page_no: int) -> str:
    encoded = quote(book_name, safe="")
    return f"/kindle_novel/images/{encoded}/{page_no:03d}.png"


def sanitize_snippet(text: str) -> str:
    """FTS5 snippet 出力を `<mark>` のみ許可する HTML として安全化する。

    1. `html.escape()` で全エスケープ
    2. `&lt;mark&gt;` / `&lt;/mark&gt;` のみを `<mark>` / `</mark>` に戻す
    """
    escaped = html.escape(text)
    return _MARK_ESCAPED.sub(r"<\1>", escaped)


def present_ranked_pages(
    pages: Sequence[RankedPage],
    main_characters: Mapping[tuple[str, int], list[str]],
) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for page in pages:
        if page.raw_snippet:
            snippet = sanitize_snippet(page.raw_snippet)
            has_highlight = "<mark>" in snippet
        else:
            snippet = html.escape((page.vector_text or "")[:200])
            has_highlight = False
        hits.append(
            SearchHit(
                book_name=page.book_name,
                page_no=page.page_no,
                snippet=snippet,
                has_highlight=has_highlight,
                image_url=_image_url(page.book_name, page.page_no),
                rrf_score=page.score,
                main_characters=main_characters.get((page.book_name, page.page_no), []),
            )
        )
    return hits


def present_full_book_pages(
    book_name: str,
    rows: Sequence[tuple[int, str | None]],
    main_characters: Mapping[tuple[str, int], list[str]],
) -> list[SearchHit]:
    return [
        SearchHit(
            book_name=book_name,
            page_no=page_no,
            snippet=full_text or "",
            has_highlight=False,
            image_url=_image_url(book_name, page_no),
            rrf_score=0.0,
            main_characters=main_characters.get((book_name, page_no), []),
        )
        for page_no, full_text in rows
    ]
