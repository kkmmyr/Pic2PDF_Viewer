"""Qwen LLM への SSE ストリーミング呼び出し（QA エンドポイント用）。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §7 と
ADR-0009（推論バックエンド切替）。

Qwen3.x 系は thinking モデルのため `stream=True` + thinking 抑制を両方そろえる
必要がある。この地雷を踏み抜く処理は共通 LLM モジュール (`D:\\61.tool\\common\\llm`
の `local_llm` パッケージ) に集約しているため、ここからは `Backend.astream_ask`
を呼ぶだけにしている。

Backend インスタンスは `_llm_backend.QWEN_BACKEND` でプロセス全体で共有される
（`config.py` の `NOVEL_DB_LLM_BACKEND` を見て llama_server / ollama を切替）。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from config import NOVEL_DB_LLM_MODEL, NOVEL_DB_QA_NUM_CTX

from ._llm_backend import build_qwen_backend
from .search import Scope, SearchHit

# プロセス起動時に Backend を作る。Backend は stateless なので使い回しで OK。
_BACKEND = build_qwen_backend()

# PoC で確定した QA 用 LLM パラメータ。num_ctx は config 化されており、B-13 段階 A〜C で
# 段階拡大（既定 32768）。
# 注意: llama-server バックエンドでは num_ctx は起動時 `-c` で決まるため、ここで
# 渡しても無視される（指定しても害はない）。env が llama_server の場合は
# start-qwen-server.bat 側で `-c 131072` を変更すること。
LLM_OPTIONS: dict[str, Any] = {
    "temperature": 0.2,
    "repeat_penalty": 1.2,
    "num_predict": 4096,
    "num_ctx": NOVEL_DB_QA_NUM_CTX,
}

PROMPT_TEMPLATE = """以下は小説『{book_title}』からの抜粋です。
これを参考にして質問に答えてください。
{summaries_block}
【回答ルール】
- 根拠としたページ番号を必ず明記してください（例: 「page 50 に記述あり」）。
- 引用する際は、誰の発言・行動・心情かを必ず明記してください。
  良い例: 「page 32 でウィラードが『～』と忠誠を誓う」「page 110 でデュークが
          自身の感情を『演技だ』と回想する」
  悪い例: 「page 110 で（主人公が）演技で自分を守る」
          （← 実際はデュークの心情なのに主人公の話として誤統合）
- 各 page には「主要登場人物: ...」のヒントが付いているので、その人物の
  発言・行動として帰属させてください。書かれていない人物の行動として推論を
  結びつけることは避けてください。
- 別々の page にあるキャラの行動を、同一人物の行動として安易に統合しないで
  ください。
- 質問が抽象的・概括的な場合（例: 「テーマ」「主人公の成長」「シリーズ全体の
  特徴」など)は、汎用的な単語の羅列で済ませず、以下を含めて構造的に深く分析
  してください:
    1. 具体的なシーン・出来事を 3 つ以上挙げる
    2. それらが示すテーマ・キャラクターの変化・物語上の意味を分析する
    3. 異なる時期・巻の対比があれば言及する
- 質問が具体的（特定のキャラ・場面・セリフ）な場合は、関連する記述を統合して
  詳しく答えてください。
- 抜粋に直接の記述がなくても、関連する複数の記述から推論して構いません。
- 書籍俯瞰サマリが与えられている場合は、それを背景知識として活用しつつ、
  page 抜粋に基づく具体的な引用を主としてください（サマリだけで答えると
  根拠ページが示せません）。
- 全く関連する記述がない場合のみ「該当箇所が見つかりません」と答えてください。

{context}

質問: {question}

回答:"""


def _strip_html(text: str) -> str:
    """`<mark>` 等の簡易タグを除去してプレーンテキスト化する。"""
    return text.replace("<mark>", "").replace("</mark>", "")


def _book_title_for_scope(scope: Scope, hits: list[SearchHit]) -> str:
    """プロンプト冒頭の書籍タイトル表示用。"""
    if scope.type == "book" and scope.id:
        return scope.id
    if scope.type == "series" and scope.id:
        return f"シリーズ「{scope.id}」（複数の書籍）"
    return "複数の書籍"


def build_prompt(
    question: str,
    hits: list[SearchHit],
    scope: Scope,
    *,
    book_summaries: dict[str, str] | None = None,
) -> str:
    """検索結果からプロンプトを組み立てる。

    Args:
        question: 質問文
        hits: ハイブリッド検索の結果
        scope: 検索スコープ
        book_summaries: `{書籍名: サマリ}` の辞書。`scope=all` / `scope=series`
            のときだけ呼び出し側で渡す。プロンプト先頭に「## 書籍俯瞰サマリ」
            セクションとして埋め込まれ、Qwen に全冊横断の俯瞰を持たせる
    """
    ctx_lines: list[str] = []
    for h in hits:
        chars_hint = ""
        if h.main_characters:
            chars_hint = f", 主要登場人物: {', '.join(h.main_characters)}"
        if scope.type == "book":
            # 単冊なら書名は省略
            header = f"[page {h.page_no}{chars_hint}]"
        else:
            header = f"[{h.book_name} page {h.page_no}{chars_hint}]"
        ctx_lines.append(f"{header}\n{_strip_html(h.snippet)}")

    context = "\n\n".join(ctx_lines)
    summaries_block = _build_summaries_block(book_summaries, scope)
    return PROMPT_TEMPLATE.format(
        book_title=_book_title_for_scope(scope, hits),
        summaries_block=summaries_block,
        context=context,
        question=question,
    )


def _build_summaries_block(
    book_summaries: dict[str, str] | None,
    scope: Scope,
) -> str:
    """書籍俯瞰サマリのプロンプトブロックを組み立てる（無ければ空文字）。

    `scope=book` のときは page 抜粋だけで足りるので含めない。
    """
    if not book_summaries or scope.type == "book":
        return ""
    lines = ["", "【書籍俯瞰サマリ】（各書籍の事前生成あらすじ。背景知識として活用）"]
    for name in sorted(book_summaries.keys()):
        lines.append(f"\n■ {name}\n{book_summaries[name]}")
    lines.append("")
    return "\n".join(lines)


async def _astream_ask(
    prompt: str,
    *,
    model: str | None = None,
    options: dict | None = None,
    timeout: float | None = None,
) -> AsyncIterator[dict]:
    """共通 Backend に委譲する thin wrapper。テストでは monkeypatch で差し替え可能。

    `stream_qa` から呼ばれる単一の入口。利用側は `_astream_ask` を直接 mock
    することで、Backend 実体（HTTP）を介さずにテストできる。
    """
    async for event in _BACKEND.astream_ask(
        prompt, model=model, options=options, timeout=timeout,
    ):
        yield event


async def stream_qa(
    prompt: str,
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    options: dict | None = None,
    timeout: float = 600.0,
) -> AsyncIterator[dict]:
    """Qwen に stream=True で投げ、各イベントを yield する。

    実体は `_llm_backend.QWEN_BACKEND.astream_ask` を呼ぶだけ。
    バックエンド分岐（Ollama / llama-server）、thinking 抑制、SSE→Ollama 形式の
    正規化はすべて共通モジュール (`local_llm`) 側に集約している。
    """
    async for event in _astream_ask(
        prompt,
        model=model,
        options=options or LLM_OPTIONS,
        timeout=timeout,
    ):
        yield event
