"""ページから主要登場人物を抽出する（Ollama gemma 経由）。

各ページのテキストを LLM に投げて、最大 3 名のキャラ名をカンマ区切りで取得する。
回答へのコンテキストヒントとして利用し、誤帰属（page 110 のデュークの行動を
レティの行動と統合する等）を抑制する。

LLM 呼び出しは Phase B（2026-05-11）以降、共通モジュール `local_llm` の
`OllamaBackend` 経由に集約。urllib 直叩きを廃止して thinking 抑制と SSE 解析を
共通モジュールに任せる。

詳細は docs/design/詳細設計/機能別/小説RAG_パイプライン設計.md §6。
"""

from __future__ import annotations

from local_llm import LLMError

from config import NOVEL_DB_CHAR_EXTRACT_MODEL

from ._llm_backend import GEMMA_BACKEND
from .character_names import parse_character_names
from .llm_options import make_llm_options

EXTRACT_PROMPT = """次の小説のページから、主要登場人物を最大 3 名挙げてください。
判断基準:
- 「主要登場人物」とは、このページ内で発言・行動・心情の主体となっている人物
- 名前が話題に上っただけで本人が登場していない人物は除外
- 該当者が居なければ「不明」と答える

出力形式:
- 名前のみをカンマ区切りで 1 行で書く（例: 「レティ, デューク」）
- 前置き・説明・敬称・補足は不要

ページテキスト:
{text}

主要登場人物（カンマ区切り）:"""

# テキスト先頭のみ送る（プロンプト長削減 + 抽出の安定性）
_TEXT_HEAD_LIMIT = 1500
_TIMEOUT_SEC = 120

# 1 ページあたりの抽出は短答型なので num_predict / num_ctx を抑える
_OPTIONS = make_llm_options(temperature=0.2, repeat_penalty=1.2, num_predict=4096, num_ctx=8192)


def extract_main_characters(
    text: str,
    *,
    model: str = NOVEL_DB_CHAR_EXTRACT_MODEL,
) -> list[str]:
    """ページテキストから主要登場人物のリストを返す（同期）。

    空文字・極端に短いテキストは [] を返して LLM 呼び出しをスキップする。
    `model` は呼び出し時に上書き可能（テストや実験で別モデルを試す用途）。
    """
    if not text or len(text.strip()) < 30:
        return []

    prompt = EXTRACT_PROMPT.format(text=text[:_TEXT_HEAD_LIMIT])
    try:
        answer = GEMMA_BACKEND.ask(prompt, model=model, options=_OPTIONS)
    except LLMError:
        return []

    return _parse_names(answer.strip())


def _parse_names(text: str) -> list[str]:
    """LLM の応答テキストから人名リストを抽出する。

    想定する応答形式:
        「レティ, デューク, アストリッド」
        「レティ、デューク」
        「不明」
        「主要登場人物: レティ, デューク」（プロンプトを反復してくる場合）
    """
    if not text:
        return []
    # 最初の改行までを採用（多くの場合 1 行で返る）
    line = text.split("\n", 1)[0].strip()
    # プロンプト反復への対策: ":" / "：" 以降を採用
    for sep in (":", "："):
        if sep in line:
            line = line.split(sep, 1)[1].strip()
    # 「不明」「該当なし」の応答
    if line in ("不明", "なし", "該当なし", "-", "－"):
        return []

    return parse_character_names(line)[:3]
