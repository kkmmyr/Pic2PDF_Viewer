"""ページ単位テキストを embedding 用にチャンク分割する。

ページ全体が短ければ 1 チャンク。長ければ句点境界優先で 800 字前後に分割し、
50 字オーバーラップさせる。
詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.2。
"""
from __future__ import annotations

MAX_CHARS = 800
OVERLAP = 50
SENTENCE_END = "。」!?"


def chunk_page(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> list[str]:
    if len(text) <= max_chars:
        stripped = text.strip()
        return [stripped] if stripped else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            # 末尾 100 字以内に句点があればそこで切る（自然な境界）
            for j in range(end, max(start + max_chars - 100, start + 1), -1):
                if text[j - 1] in SENTENCE_END:
                    end = j
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
