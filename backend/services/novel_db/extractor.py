"""PDF からページ単位のテキストを抽出する。

PyMuPDF の get_text("blocks") で縦書き 1 列 = 1 ブロックとして取得し、
各ブロック内の改行（縦書き 1 文字 TextObject 配置の副作用）を除去してから連結する。
詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.1。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

import fitz

_NEWLINE_RE = re.compile(r"\n+")


class PageText(TypedDict):
    page_no: int        # 1-indexed
    full_text: str
    char_count: int


def extract_pages(pdf_path: str | Path) -> list[PageText]:
    pages: list[PageText] = []
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc):
            blocks = page.get_text("blocks")
            parts: list[str] = []
            for b in blocks:
                # blocks タプルの 5 要素目がテキスト本体（PyMuPDF API）
                cleaned = _NEWLINE_RE.sub("", b[4]).strip()
                if cleaned:
                    parts.append(cleaned)
            full_text = "\n".join(parts)
            pages.append({
                "page_no": i + 1,
                "full_text": full_text,
                "char_count": len(full_text),
            })
    return pages
