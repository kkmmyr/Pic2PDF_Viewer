#!/usr/bin/env python3
"""mcp_server.py - Qwen3.6 MCPサーバー。

Claude Code から Qwen3.6:35b-a3b（thinking モデル）をツールとして呼び出す。
Gemma 4:e4b より重い分、長文の検証・複雑な分析・難しいコードレビュー等に使う想定。

起動方法:  python mcp_server.py
登録方法:  ~/.mcp.json の mcpServers に "qwen-local" を追加（README 参照）
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from mcp.types import Completion

from local_llm import LLMError, backend_from_env
from local_llm.logger import log_interaction

# 環境変数 (QWEN_BACKEND / QWEN_OLLAMA_BASE_URL / ...) から Backend を 1 つ作る
_BACKEND = backend_from_env()

# Pic2PDF_Viewer バックエンド API（書籍 / キャラクター Resources 用）
_NOVEL_API_BASE = os.environ.get("NOVEL_DB_BASE_URL", "http://localhost:8766")


def _fetch_json(path: str) -> list | dict | None:
    """バックエンド API を GET して JSON を返す。接続失敗時は None。"""
    url = f"{_NOVEL_API_BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


mcp = FastMCP(
    "qwen-local",
    instructions=(
        "ローカルで動作する Qwen3.6:35b-a3b（thinking モデル）へのアクセスを提供します。"
        "Gemma より高品質ですが応答時間は長め（1 問 ~120 秒）。"
        "複雑な分析・長文の検証・コードレビュー・推論を要する質問に使用してください。"
        "単純な説明・翻訳・コード生成などは gemma-local を優先してください。"
    ),
)


def _call_qwen(prompt: str, *, system: str | None, source: str) -> str:
    """共通 LLM Backend を呼んで応答を返し、ログに記録する。"""
    started = time.monotonic()
    try:
        response = _BACKEND.ask(prompt, system=system)
    except LLMError as e:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_interaction(source, prompt, f"[ERROR] {e}", elapsed_ms)
        return f"[エラー] Qwen 呼び出しに失敗しました: {e}"
    elapsed_ms = int((time.monotonic() - started) * 1000)
    log_interaction(source, prompt, response, elapsed_ms)
    return response


@mcp.tool()
def ask_qwen(prompt: str, system: str | None = None) -> str:
    """ローカルの Qwen3.6:35b-a3b に質問する。

    複雑な分析・推論・長文検討に適しています。
    1 リクエスト ~120 秒かかるため、単純なタスクは gemma-local を優先してください。

    向いているタスク:
    - 設計判断のセカンドオピニオン
    - 複雑なロジックの妥当性検証
    - 長文・多視点の要約や論点抽出
    - 日本語の高度な読解（小説・論文・契約書など）

    Args:
        prompt: 質問またはタスクの内容
        system: 任意のシステムプロンプト（役割設定など）
    """
    return _call_qwen(prompt, system=system, source="mcp:ask_qwen")


@mcp.tool()
def analyze_code(
    code: str, question: str = "このコードの問題点と改善案を指摘してください"
) -> str:
    """Qwen3.6 にコードの分析・レビューを依頼する。

    Gemma の explain_code よりも踏み込んだ分析（バグ発見・代替実装の提案・
    パフォーマンス考察など）に向いています。1 ファイル内のコードを対象とし、
    複数ファイルにまたがる文脈は呼び出し側で context として渡してください。

    Args:
        code: 分析対象のコード
        question: コードに対する質問・指示（デフォルト: 問題点と改善案の指摘）
    """
    prompt = (
        f"以下のコードについて、{question}\n"
        "根拠とともに具体的に指摘してください。\n\n"
        f"```\n{code}\n```"
    )
    return _call_qwen(prompt, system=None, source="mcp:analyze_code")


@mcp.tool()
def analyze_long_text(text: str, instruction: str) -> str:
    """Qwen3.6 に長文の分析・要約・論点抽出を依頼する。

    Qwen は日本語の長文読解に強く、num_ctx=8192 まで読み込めます。
    小説・記事・議事録・調査資料などの構造的な分析に向いています。

    Args:
        text: 分析対象のテキスト
        instruction: 分析の指示（例: 「この章の主題を 3 点に整理して」「論点ごとに賛否をまとめて」）
    """
    prompt = (
        "以下のテキストについて、指示に従って分析してください。\n"
        "根拠としたテキスト中の表現は引用しながら、構造的に答えてください。\n\n"
        f"【指示】\n{instruction}\n\n"
        f"【テキスト】\n{text}"
    )
    return _call_qwen(prompt, system=None, source="mcp:analyze_long_text")


# ---------------------------------------------------------------------------
# Resources: Pic2PDF_Viewer 小説データ（バックエンド :8766 起動中のみ有効）
# ---------------------------------------------------------------------------

_BACKEND_UNAVAILABLE = (
    "バックエンドサーバー（:8766）に接続できません。\n"
    "`cd backend && uv run uvicorn main:app --reload --port 8766` で起動してください。"
)


@mcp.resource(
    "novel://books",
    name="小説書籍一覧",
    description="Pic2PDF_Viewer に登録された小説の一覧（タイトル・著者・シリーズ・インデックス状態）。",
    mime_type="text/plain",
)
def novel_books() -> str:
    """書籍一覧を返す。バックエンドが起動していない場合はエラーメッセージ。"""
    data = _fetch_json("/api/novel_db/books")
    if data is None:
        return _BACKEND_UNAVAILABLE

    lines = ["# 小説書籍一覧\n"]
    for b in data:
        status = "indexed" if b.get("is_indexed") else "未インデックス"
        authors = "、".join(b.get("authors") or []) or "著者不明"
        series = f" [{b['series_title']}]" if b.get("series_title") else ""
        pages = f" {b['page_count']}p" if b.get("page_count") else ""
        lines.append(f"- **{b['name']}**{series}  {authors}  {status}{pages}")
    return "\n".join(lines)


@mcp.resource(
    "novel://characters/{book_name}",
    name="キャラクター辞典",
    description="指定書籍のキャラクター一覧（名前・初登場ページ・登場ページ数・サマリ有無）。",
    mime_type="text/plain",
)
def novel_characters(book_name: str) -> str:
    """指定書籍のキャラクター一覧を返す。"""
    encoded = quote(book_name, safe="")
    data = _fetch_json(f"/api/novel_db/books/{encoded}/characters")
    if data is None:
        return _BACKEND_UNAVAILABLE
    if not data:
        return f"書籍「{book_name}」にはまだキャラクター辞典が生成されていません。"

    lines = [f"# {book_name} キャラクター一覧\n"]
    for c in data:
        summary_status = "サマリあり" if c.get("has_summary") else "サマリ未生成"
        lines.append(
            f"- **{c['name']}**  初登場 p.{c['first_page']}  "
            f"{c['page_count']}ページに登場  {summary_status}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompts: 書籍名補完付きスラッシュコマンド
# ---------------------------------------------------------------------------


@mcp.prompt(
    name="novel-qa",
    description=(
        "小説の内容について質問する。"
        "book_name で書籍を指定（補完あり）、question で質問内容を入力。"
        "書籍のサマリ・著者・キャラクター数をコンテキストに載せる。"
    ),
)
def novel_qa_prompt(book_name: str, question: str) -> list[dict]:
    """指定書籍のメタ情報をコンテキストに追加して質問を立てるプロンプト。"""
    detail = _fetch_json(f"/api/novel_db/books/{quote(book_name, safe='')}")

    if detail is None:
        context = _BACKEND_UNAVAILABLE
    else:
        authors = "、".join(detail.get("authors") or []) or "著者不明"
        series = (
            f"シリーズ: {detail['series_title']}  "
            if detail.get("series_title")
            else ""
        )
        page_count = detail.get("page_count") or "不明"
        char_count = detail.get("character_count", 0)
        summary = detail.get("summary") or "（書籍サマリ未生成）"
        context = (
            f"【書籍情報】\n"
            f"タイトル: {book_name}  著者: {authors}  {series}{page_count}ページ  "
            f"登録キャラクター: {char_count}人\n\n"
            f"【書籍サマリ】\n{summary}"
        )

    return [
        {
            "role": "user",
            "content": f"{context}\n\n【質問】\n{question}",
        }
    ]


@mcp.prompt(
    name="summarize-book",
    description=(
        "指定書籍のサマリ・著者・キャラクター数を表示する。"
        "book_name で書籍を指定（補完あり）。"
    ),
)
def summarize_book_prompt(book_name: str) -> list[dict]:
    """指定書籍の詳細情報をまとめて表示するプロンプト。"""
    detail = _fetch_json(f"/api/novel_db/books/{quote(book_name, safe='')}")

    if detail is None:
        return [{"role": "user", "content": _BACKEND_UNAVAILABLE}]

    authors = "、".join(detail.get("authors") or []) or "著者不明"
    series = (
        f"\nシリーズ: {detail['series_title']}" if detail.get("series_title") else ""
    )
    page_count = detail.get("page_count") or "不明"
    char_count = detail.get("character_count", 0)
    summary = detail.get("summary") or "まだ書籍サマリが生成されていません。"

    body = (
        f"# {book_name}\n"
        f"著者: {authors}{series}\n"
        f"{page_count}ページ  |  登録キャラクター: {char_count}人\n\n"
        f"## 書籍サマリ\n{summary}"
    )
    return [{"role": "user", "content": body}]


@mcp.completion()
def handle_completion(ref, argument, context):  # noqa: ANN001
    """novel-qa / summarize-book の book_name 引数に書籍名補完を返す。"""
    if argument.name != "book_name":
        return None
    data = _fetch_json("/api/novel_db/books")
    if not data:
        return Completion(values=[])
    partial = argument.value.lower()
    matches = [b["name"] for b in data if partial in b["name"].lower()]
    return Completion(values=matches[:20], hasMore=len(matches) > 20)


if __name__ == "__main__":
    mcp.run()
