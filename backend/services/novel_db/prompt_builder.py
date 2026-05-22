"""QA / chat 用プロンプト組み立て。

LLM 呼び出し（stream_qa / stream_chat）とは独立した純関数群。
プロンプトテンプレートと context 整形ロジックをここに集約し、
llm.py はストリーミング呼び出しのみを担う。
"""
from __future__ import annotations

from typing import Any

from .search import Scope, SearchHit

# QA 用プロンプトテンプレート
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

# 会話用 system プロンプト（1 セッション 1 回・初手で必ず挿入）
CHAT_SYSTEM_TEMPLATE = """あなたは小説作品の読書補助アシスタントです。
以下の方針で会話的に質問に答えてください。

- 根拠としたページ番号を必ず明記する（例: 「page 50 に記述あり」）。
- 引用するときは誰の発言・行動・心情かを明示する。別キャラの内面を主人公に
  誤って統合しない。
- 直前のやりとり（過去の質問・回答）の文脈を踏まえ、同じ内容を繰り返さず、
  深掘りや視点切替に応じる。
- 抜粋に直接の記述がなくても、関連する記述から推論してよいが、推論である
  ことを明示する。
- 関連する記述がまったく無い場合のみ「該当箇所が見つかりません」と答える。

【会話対象スコープ】
{scope_block}

【参照可能な本文・俯瞰サマリ】（初手で提示する。以降のターンでも参照可）
{context_block}
"""


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


def _format_scope_line(scope: Any) -> str:
    """scope を会話 system メッセージで表示するための 1 行説明に整形する。"""
    if scope.type == "book" and scope.id:
        return f"単冊「{scope.id}」"
    if scope.type == "series" and scope.id:
        return f"シリーズ「{scope.id}」"
    return "全 novel ライブラリ"


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


def build_chat_context_block(
    hits: list[SearchHit],
    scope: Scope,
    *,
    book_summaries: dict[str, str] | None = None,
) -> str:
    """B-16: chat 用の本文 + 俯瞰サマリブロックを 1 つの文字列に組み立てる。

    `build_prompt` の context + summaries 部分と同じ整形ロジックを使うが、
    質問文や回答ルールは含めない（system プロンプトのテンプレ側に書く）。
    """
    ctx_lines: list[str] = []
    for h in hits:
        chars_hint = ""
        if h.main_characters:
            chars_hint = f", 主要登場人物: {', '.join(h.main_characters)}"
        if scope.type == "book":
            header = f"[page {h.page_no}{chars_hint}]"
        else:
            header = f"[{h.book_name} page {h.page_no}{chars_hint}]"
        ctx_lines.append(f"{header}\n{_strip_html(h.snippet)}")

    context = "\n\n".join(ctx_lines)
    summaries_block = _build_summaries_block(book_summaries, scope)
    if summaries_block:
        return f"{summaries_block}\n\n{context}"
    return context


def build_chat_system_message(
    scope: Any,
    *,
    context_block: str,
) -> str:
    """会話セッション開始時に投入する system メッセージ。

    `scope` は `Scope`（`type` + `id`）。`context_block` は単発 QA と同じ手順で
    組み立てた本文抜粋 + 書籍俯瞰サマリ（呼び出し側で `build_prompt`
    互換のフォーマット）。
    """
    scope_line = _format_scope_line(scope)
    return CHAT_SYSTEM_TEMPLATE.format(
        scope_block=scope_line,
        context_block=context_block,
    )
