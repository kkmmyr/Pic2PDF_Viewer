"""B-9 Contextual Retrieval: 各チャンクに「書籍内の位置説明」を付与する。

Anthropic 2024-09 ブログの Contextual Retrieval 手法を踏襲。各チャンクに対して
書籍俯瞰サマリ（B-5）をコンテキストとして与え、LLM に「このチャンクが書籍内の
どの場面か」を 1 文（~80 字）で生成させる。`(contextual_text + chunk_text)` を
bge-m3 で再 embedding すると、retrieval の recall が大きく改善する（Anthropic 計
測で 35〜49% 改善）。

LLM 選定:
- 単純な位置説明タスクなので軽量モデルで十分
- 既定: `gemma4:e4b`（NOVEL_DB_CONTEXT_MODEL）
- 品質不足なら `qwen3.6:35b-a3b` にフォールバック（環境変数で切替）

LLM 呼び出しは Phase B（2026-05-11）以降、共通モジュール `local_llm` の
`OllamaBackend` 経由に集約。

詳細は docs/log/計画/バックログ.md B-9 / docs/design/詳細設計/機能別/小説RAG_パイプライン設計.md §5（書籍サマリベクトル
検索）と並ぶ「検索品質改善 2 段目」。
"""

from __future__ import annotations

from local_llm import LLMError

from config import NOVEL_DB_BODY_PAGE_MARGIN, NOVEL_DB_CONTEXT_MODEL, NOVEL_DB_MIN_BODY_CHARS

from .llm_options import make_llm_options
from .llm_provider import NovelLlmProvider, get_llm_provider

# Anthropic 流のプロンプト。書名・俯瞰サマリ・チャンク本文を与えて
# 「retrieval のための簡潔な位置説明」を返してもらう。
#
# 2026-05-12 改良: 物語的要約に流れて固有名詞が落ちる事例が頻発したため、
# 本文に登場する固有名詞と特徴的フレーズを **必ず** 含めるよう明示指示を追加。
# 例: Vol 9 p113「ベルナードの教え 国民への義務」が ctx に入らず検索沈降した事例。
_CONTEXT_PROMPT = """以下は小説『{book_name}』の俯瞰サマリと、その本文中の特定の抜粋（チャンク）です。
このチャンクが書籍内のどの場面に位置するかを、検索のための位置説明として 1 文で書いてください。

必ず含めるべきこと（最重要）:
- **チャンク本文に登場する固有名詞**（人名・組織名・地名・役職など）を可能な限り入れる
- **特徴的なフレーズや言い回し**（教え・誓い・決め台詞・象徴的な単語）を 1 つ以上拾う
  → 物語要約に丸めて固有名詞や引用句を捨てない。検索クエリは固有名詞でヒットさせる前提

そのうえで含めるべき情報:
- 書名（または「〇巻」のような巻数）
- 場面の種類（戦闘 / 対話 / 内省 / 回想 / 計画 など）
- 何が起きているかの一言

避けるべきこと:
- 前置き（「以下が〜」「このチャンクは〜」等)
- 余計な解説・感想

【俯瞰サマリ】
{book_summary}

【チャンク】
{chunk_text}

【出力】1 文（80〜120 字程度）、本文の固有名詞と特徴的フレーズを含めた位置説明のみ:"""

_MAX_CHUNK_CHARS = 1200  # チャンク先頭のみを送信（プロンプト長を抑える）

# 80 字程度の位置説明 + 余裕。短答型のため num_predict / num_ctx を抑える
_OPTIONS = make_llm_options(temperature=0.2, repeat_penalty=1.15, num_predict=256, num_ctx=8192)


def generate_chunk_context(
    book_name: str,
    book_summary: str,
    chunk_text: str,
    *,
    model: str = NOVEL_DB_CONTEXT_MODEL,
    provider: NovelLlmProvider | None = None,
) -> str:
    """1 チャンクの位置説明を生成して返す（同期）。

    Args:
        book_name: 書籍名（プロンプトに含める）
        book_summary: B-5 で生成された書籍俯瞰サマリ
        chunk_text: チャンク本文（先頭 _MAX_CHUNK_CHARS 字までに切り詰める）
        model: 使用モデル（デフォルトは config の NOVEL_DB_CONTEXT_MODEL）

    Returns:
        位置説明テキスト（前後の空白除去済み）。失敗時は空文字。

    生成失敗（接続エラー / 空応答 / タイムアウト）時は空文字を返す。呼び出し側は
    空文字なら「このチャンクは未 contextualize」として扱い、次回の `--redo` を待つ。
    """
    if not chunk_text or not chunk_text.strip():
        return ""
    if not book_summary or not book_summary.strip():
        # サマリが無い書籍ではコンテキスト生成をスキップ（B-5 が前提）
        return ""

    prompt = _CONTEXT_PROMPT.format(
        book_name=book_name,
        book_summary=book_summary,
        chunk_text=chunk_text[:_MAX_CHUNK_CHARS],
    )
    try:
        answer = (provider or get_llm_provider()).gemma.ask(prompt, model=model, options=_OPTIONS)
    except LLMError:
        return ""

    return _clean_response(answer)


def _clean_response(text: str) -> str:
    """LLM 応答の前置き / 改行 / 終端句読点を整形する。"""
    text = text.strip()
    if not text:
        return ""
    # 「位置説明:」「場面:」のような前置きを除去
    for prefix in ("位置説明:", "位置説明：", "場面:", "場面：", "出力:", "出力："):
        if text.startswith(prefix):
            text = text[len(prefix) :].lstrip()
    # 1 行目だけ採用（複数行返ってくる場合の保険）
    return text.split("\n", 1)[0].strip()


def make_embedding_input(contextual_text: str | None, chunk_text: str) -> str:
    """chunks_vec に投入する embedding 入力を組み立てる。

    contextual_text が空 / NULL のチャンクは text のみで embedding する
    （後方互換: B-9 未適用チャンクも従来通り検索対象に残せる）。
    """
    if contextual_text and contextual_text.strip():
        return f"{contextual_text.strip()}\n\n{chunk_text}"
    return chunk_text


def should_skip_context(char_count: int, page_no: int, page_count: int) -> bool:
    """ctx 生成を skip すべきチャンクか判定する（B-9 改良 2026-05-12）。

    skip 条件:
    - char_count < NOVEL_DB_MIN_BODY_CHARS (300): 章扉・目次など薄いチャンク
    - page_no が先頭・末尾 NOVEL_DB_BODY_PAGE_MARGIN (5) ページ以内: 表紙・あとがき等

    skip 対象は ctx を NULL に保ち、検索 noise を避ける。
    """
    if char_count < NOVEL_DB_MIN_BODY_CHARS:
        return True
    margin = NOVEL_DB_BODY_PAGE_MARGIN
    return page_no <= margin or page_no > page_count - margin
