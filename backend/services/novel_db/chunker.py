"""ページ単位テキストを embedding 用にチャンク分割する。

chunk_page()  : 【本番】1 ページの文字列 → チャンクリスト（800 字 / overlap 50 字）
chunk_book()  : 【§4.4 実験用】全ページ連結クロスページチャンク（1200 字 / overlap 120 字）
                eval_chunk_strategy.py での比較検証後に本番採否を決定する。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.2。
"""

from __future__ import annotations

import bisect

MAX_CHARS = 800
OVERLAP = 50

MAX_CHARS_BOOK = 1200
OVERLAP_BOOK = 120

SENTENCE_END = "。」!?"


def chunk_page(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> list[str]:
    """1 ページのテキストをチャンク分割する（後方互換 API）。"""
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


def chunk_book(
    pages: list[dict],
    *,
    max_chars: int = MAX_CHARS_BOOK,
    overlap: int = OVERLAP_BOOK,
    min_page_chars: int = 30,
) -> list[dict]:
    """全ページを連結してクロスページチャンクを生成する（§4.4）。

    ページ境界を越えたチャンクを作ることで、ページ末尾/先頭で意味が切れる問題を回避する。

    Args:
        pages: [{"page_id": int, "page_no": int, "full_text": str}]
               page_no 昇順でソート済みを期待する（SQL の ORDER BY page_no を保証）。
        max_chars: チャンクの最大文字数（デフォルト 1200）。
        overlap: 隣接チャンク間のオーバーラップ文字数（デフォルト 120）。
        min_page_chars: これより短いページはスキップ（章扉・ヘッダのみ等）。

    Returns: [{"page_id": int, "chunk_idx": int, "text": str}]
             page_id = チャンクが開始するページの id。リーダーへのジャンプに使う。
    """
    valid = [p for p in pages if len(p.get("full_text") or "") >= min_page_chars]
    if not valid:
        return []

    # 全ページを 1 本に連結し、各ページの開始オフセットを記録
    full_text = ""
    page_starts: list[tuple[int, int]] = []  # (char_offset, page_id)
    for p in valid:
        page_starts.append((len(full_text), p["page_id"]))
        full_text += p.get("full_text") or ""

    if not full_text.strip():
        return []

    offsets = [s[0] for s in page_starts]

    def _page_id_at(offset: int) -> int:
        idx = bisect.bisect_right(offsets, offset) - 1
        return page_starts[max(idx, 0)][1]

    window = max(max_chars // 10, 50)
    chunks: list[dict] = []
    chunk_idx = 0
    start = 0
    while start < len(full_text):
        end = min(start + max_chars, len(full_text))
        if end < len(full_text):
            for j in range(end, max(start + max_chars - window, start + 1), -1):
                if full_text[j - 1] in SENTENCE_END:
                    end = j
                    break
        text = full_text[start:end].strip()
        if text:
            chunks.append({"page_id": _page_id_at(start), "chunk_idx": chunk_idx, "text": text})
            chunk_idx += 1
        if end >= len(full_text):
            break
        start = max(end - overlap, start + 1)

    return chunks
