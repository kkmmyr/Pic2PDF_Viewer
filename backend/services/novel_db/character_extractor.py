"""ページから主要登場人物を抽出する（Ollama gemma 経由）。

各ページのテキストを LLM に投げて、最大 3 名のキャラ名をカンマ区切りで取得する。
回答へのコンテキストヒントとして利用し、誤帰属（page 110 のデュークの行動を
レティの行動と統合する等）を抑制する。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from config import NOVEL_DB_CHAR_EXTRACT_MODEL, NOVEL_DB_OLLAMA_BASE_URL

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


def extract_main_characters(
    text: str, *, model: str = NOVEL_DB_CHAR_EXTRACT_MODEL
) -> list[str]:
    """ページテキストから主要登場人物のリストを返す（同期）。

    空文字・極端に短いテキストは [] を返して LLM 呼び出しをスキップする。

    `gemma4:26b` 等の thinking モデルを使うと、thinking ブロックで num_predict を
    消費して response が空になることがある。デフォルトでは軽量な `gemma4:e4b` を
    使用し、加えて `think=false` を渡して thinking を抑止する。
    """
    if not text or len(text.strip()) < 30:
        return []

    prompt = EXTRACT_PROMPT.format(text=text[:_TEXT_HEAD_LIMIT])
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": True,
        "think": False,  # thinking モデル対応（無視されても安全）
        "options": {
            "temperature": 0.2,
            "repeat_penalty": 1.2,
            "num_predict": 4096,
            "num_ctx": 8192,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{NOVEL_DB_OLLAMA_BASE_URL}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    response_parts: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("response"):
                    response_parts.append(event["response"])
                if event.get("done"):
                    break
    except urllib.error.URLError:
        return []

    answer = "".join(response_parts).strip()
    return _parse_names(answer)


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

    # カンマ・読点・スペースで分割
    raw = line.replace("、", ",").replace("・", ",")
    names: list[str] = []
    for part in raw.split(","):
        cleaned = part.strip().strip("「」『』\"'.。 ")
        if not cleaned or cleaned in ("不明", "なし"):
            continue
        # 過度に長い断片（説明文）はスキップ
        if len(cleaned) > 30:
            continue
        names.append(cleaned)
    return names[:3]
