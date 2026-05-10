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

詳細は docs/01_要件定義/機能追加候補.md B-9 / 同設計書 §6.5（書籍サマリベクトル
検索）と並ぶ「検索品質改善 2 段目」。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from config import NOVEL_DB_CONTEXT_MODEL, NOVEL_DB_OLLAMA_BASE_URL

# Anthropic 流のプロンプト。書名・俯瞰サマリ・チャンク本文を与えて
# 「retrieval のための簡潔な位置説明」を返してもらう。
_CONTEXT_PROMPT = """以下は小説『{book_name}』の俯瞰サマリと、その本文中の特定の抜粋（チャンク）です。
このチャンクが書籍内のどの場面に位置するかを、検索のための位置説明として 1 文で書いてください。

含めるべき情報:
- 書名（または「〇巻」のような巻数）
- 主要な登場人物
- 場面の種類（戦闘 / 対話 / 内省 / 回想 / 計画 など）
- 何が起きているかの一言

避けるべきこと:
- 前置き（「以下が〜」「このチャンクは〜」等）
- チャンク本文の引用そのまま
- 余計な解説

【俯瞰サマリ】
{book_summary}

【チャンク】
{chunk_text}

【出力】1 文（80 字程度）、位置説明のみ:"""

_TIMEOUT_SEC = 120
_MAX_CHUNK_CHARS = 1200  # チャンク先頭のみを送信（プロンプト長を抑える）


def generate_chunk_context(
    book_name: str,
    book_summary: str,
    chunk_text: str,
    *,
    model: str = NOVEL_DB_CONTEXT_MODEL,
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
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": True,
        "think": False,
        "options": {
            "temperature": 0.2,
            "repeat_penalty": 1.15,
            "num_predict": 256,   # 80 字程度の位置説明 + 余裕
            "num_ctx": 8192,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{NOVEL_DB_OLLAMA_BASE_URL}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            parts: list[str] = []
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("response"):
                    parts.append(event["response"])
                if event.get("done"):
                    break
            return _clean_response("".join(parts))
    except urllib.error.URLError:
        return ""


def _clean_response(text: str) -> str:
    """LLM 応答の前置き / 改行 / 終端句読点を整形する。"""
    text = text.strip()
    if not text:
        return ""
    # 「位置説明:」「場面:」のような前置きを除去
    for prefix in ("位置説明:", "位置説明：", "場面:", "場面：", "出力:", "出力："):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
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
