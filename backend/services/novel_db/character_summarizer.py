"""B-15 キャラクター辞典: Qwen によるキャラクター人物像サマリ生成。

DB アクセス（book_characters テーブルの CRUD・集計）は character_db.py を参照。
"""

from __future__ import annotations

from collections.abc import Callable

from config import NOVEL_DB_LLM_MODEL

from .generation_quality import format_page_blocks, select_pages_across_book
from .llm_options import make_llm_options
from .llm_provider import NovelLlmProvider, get_llm_provider

_PROMPT = """次は小説『{book_name}』から「{char_name}」が登場するページを page_no 順に集めた本文です。
この本（1 冊）における「{char_name}」の人物像を、初めて読む人にも分かる
自然な文章で説明してください。

含めるべき要素:
- 最初に、誰でどのような役職・立場にあり、他キャラとどう関係するか
- この巻における主要な行動・選択と、その理由や心情の動き
- 他キャラとの関係性の変化があれば明記
- この巻の物語で果たす役割
- 本文で確実に確認できる場合だけ、理解を助ける台詞や象徴的なフレーズ

避けること:
- 場面の単純な羅列（「page X で Y した」の連続）
- 本文の長い引用
- 「彼 / 彼女」だけで言い換える曖昧化、主語の省略
- 文字数に合わせるための電文調、名詞句の連結、説明不足
- 本文にない設定・関係・心情の推測

長さや段落数は指定しません。重要人物は話題ごとに段落を分け、必要な情報を
省略しないでください。登場量が少ない人物は、情報を水増しせず確認できる範囲を
明瞭に説明してください。

事実抽出工程の人物メモ:
{fact_notes}

本文（page_no 順、抜粋）:
{body}

『{book_name}』における「{char_name}」の人物像:"""

_EDITOR_PROMPT = """次は小説『{book_name}』における「{char_name}」の人物説明の初稿です。
事実メモと照合し、初めて読む人にも人物の立場・関係・行動・変化が分かる自然な文章へ
校正してください。

修正すること:
- 冒頭で「{char_name}」が誰で、どの立場か分からない
- 主語の省略、曖昧な代名詞、関係する相手が不明な表現
- 行動と理由、出来事と関係変化のつながりが不明
- 電文調、名詞句の連結、同内容の反復、不自然な圧縮

禁止:
- 事実メモや初稿にない設定・関係・心理を追加する
- 人物名「{char_name}」を本文から消す
- ページ番号、生成マーカー、コードフェンス、「修正版」等のラベルを出す
- 文字数や段落数を目標にして情報を削る

事実メモ:
{fact_notes}

初稿:
{draft}

完成した人物説明だけを出力してください:"""

# 主要キャラの body は 80k 字（_MAX_BODY_CHARS）まで取り得る ≒ ~50k tokens。
# B-14 の llama-server は num_ctx=131072 起動なので余裕を持って 65536。
_OPTIONS = make_llm_options(temperature=0.2, repeat_penalty=1.15, num_predict=2048, num_ctx=65536)
_EDITOR_OPTIONS = make_llm_options(temperature=0.15, repeat_penalty=1.15, num_predict=2048, num_ctx=16384)

# 1 キャラの page を全部連結したときの上限（Qwen num_ctx に余裕を持たせる）。
_MAX_BODY_CHARS = 80_000


def summarize_character(
    book_name: str,
    char_name: str,
    pages: list[tuple[int, str]],
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    fact_notes: str = "",
    progress: Callable[[str], None] | None = None,
    provider: NovelLlmProvider | None = None,
) -> str:
    """1 キャラ × 1 書籍の人物像サマリを Qwen で生成して返す（DB には書き込まない）。

    Raises:
        ValueError: pages が空。
        LLMError: Qwen 呼び出しに失敗。
    """
    if not pages:
        raise ValueError(f"no pages collected for character: {char_name}")

    selected_pages = select_pages_across_book(pages, max_chars=_MAX_BODY_CHARS)
    if progress is not None and len(selected_pages) < len(pages):
        progress(
            f"    selected {len(selected_pages)}/{len(pages)} evidence pages (first/final + temporal coverage)",
        )

    body = format_page_blocks(selected_pages)
    prompt = _PROMPT.format(
        book_name=book_name,
        char_name=char_name,
        fact_notes=fact_notes or "本文から抽出した追加メモなし。",
        body=body,
    )
    return (provider or get_llm_provider()).qwen.ask(prompt, model=model, options=_OPTIONS).strip()


def edit_character_summary(
    book_name: str,
    char_name: str,
    draft: str,
    *,
    fact_notes: str,
    model: str = NOVEL_DB_LLM_MODEL,
    provider: NovelLlmProvider | None = None,
) -> str:
    """Run a separate editorial pass without adding unsupported facts."""
    prompt = _EDITOR_PROMPT.format(
        book_name=book_name,
        char_name=char_name,
        fact_notes=fact_notes,
        draft=draft,
    )
    return (provider or get_llm_provider()).qwen.ask(prompt, model=model, options=_EDITOR_OPTIONS).strip()
