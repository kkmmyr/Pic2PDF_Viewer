"""B-15 キャラクター辞典: Qwen によるキャラクター人物像サマリ生成。

DB アクセス（book_characters テーブルの CRUD・集計）は character_db.py を参照。
"""
from __future__ import annotations

from collections.abc import Callable

from config import NOVEL_DB_LLM_MODEL

from ._llm_backend import QWEN_BACKEND
from .character_db import CharacterRow, CharacterStat  # noqa: F401 (re-export)

_PROMPT = """次は小説『{book_name}』から「{char_name}」が登場するページを page_no 順に集めた本文です。
この本（1 冊）における「{char_name}」の人物像を、1 段落（{target} 字程度）でまとめてください。

含めるべき要素:
- 役職・立場・他キャラとの関係（誰の誰か、どの組織の誰か）
- この巻における主要な行動・選択・心情の動き
- 他キャラとの関係性の変化があれば明記
- 印象的な台詞・象徴的なフレーズがあれば 1 つ引用

避けること:
- 場面の単純な羅列（「page X で Y した」の連続）
- 本文の長い引用
- 「彼 / 彼女」だけで言い換える曖昧化

本文（page_no 順、抜粋）:
{body}

『{book_name}』における「{char_name}」の人物像（{target} 字程度、1 段落）:"""

_TARGET_CHARS = 400

_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.15,
    "num_predict": 1024,   # 400 字 + 余裕
    # 主要キャラの body は 80k 字（_MAX_BODY_CHARS）まで取り得る ≒ ~50k tokens。
    # B-14 の llama-server は num_ctx=131072 起動なので余裕を持って 65536。
    "num_ctx": 65536,
}

# 1 キャラの page を全部連結したときの上限（Qwen num_ctx に余裕を持たせる）。
_MAX_BODY_CHARS = 80_000


def summarize_character(
    book_name: str,
    char_name: str,
    pages: list[tuple[int, str]],
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    progress: Callable[[str], None] | None = None,
) -> str:
    """1 キャラ × 1 書籍の人物像サマリを Qwen で生成して返す（DB には書き込まない）。

    Raises:
        ValueError: pages が空。
        LLMError: Qwen 呼び出しに失敗。
    """
    if not pages:
        raise ValueError(f"no pages collected for character: {char_name}")

    # page_no 順に連結（過剰に長ければ末尾を切る）
    blocks: list[str] = []
    total_chars = 0
    for page_no, text in pages:
        block = f"[page {page_no}]\n{text}"
        if total_chars + len(block) > _MAX_BODY_CHARS:
            if progress is not None:
                progress(
                    f"    body limit {_MAX_BODY_CHARS:,} chars reached "
                    f"after page {page_no} (truncated)",
                )
            break
        blocks.append(block)
        total_chars += len(block) + 2  # 区切り改行分の概算

    body = "\n\n".join(blocks)
    prompt = _PROMPT.format(
        book_name=book_name, char_name=char_name, body=body, target=_TARGET_CHARS,
    )
    return QWEN_BACKEND.ask(prompt, model=model, options=_OPTIONS).strip()
