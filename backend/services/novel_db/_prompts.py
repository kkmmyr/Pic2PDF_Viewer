"""書籍サマリ生成用プロンプトテンプレート・LLM オプション・定数。

summarizer.py が使うすべてのプロンプト文字列と設定値をここに一元管理する。
プロンプトを修正する場合はこのファイルだけ変更すればよい。
"""

from __future__ import annotations

import re

from .llm_options import make_llm_options

# ---------------------------------------------------------------------------
# 閾値・サイズ定数
# ---------------------------------------------------------------------------

# 1-shot 経路で許容する最大本文文字数。超えたら map-reduce にフォールバック。
# Qwen は ~1.6 chars/token なので 200,000 字 ≒ 125k tokens。num_ctx=131072 でぎりぎり。
ONE_SHOT_MAX_BODY_CHARS = 200_000

# map フェーズの 1 チャンクあたりの目標文字数
MAP_CHUNK_TARGET_CHARS = 20_000

# map フェーズの最大チャンク数（過大な書籍でも 8 チャンク以内に抑える）
MAP_MAX_CHUNKS = 8

# reduce フェーズ / 1-shot フェーズの目標サマリ長
FINAL_SUMMARY_TARGET_CHARS = 1500

# 一括生成（書籍サマリ + キャラクター辞典）の定数
CHAR_SUMMARY_TARGET_CHARS = 400
COMBINED_MAX_CHARACTERS = 20

# ---------------------------------------------------------------------------
# LLM オプション
# ---------------------------------------------------------------------------

ONE_SHOT_OPTIONS = make_llm_options(
    temperature=0.2,
    repeat_penalty=1.15,
    num_predict=2560,  # 1500 字サマリ + 余裕
    num_ctx=131072,  # B-6 検証で 70k tokens 完走を確認（2026-05-10）
)

MAP_OPTIONS = make_llm_options(temperature=0.2, repeat_penalty=1.15, num_predict=768, num_ctx=16384)

REDUCE_OPTIONS = make_llm_options(temperature=0.2, repeat_penalty=1.15, num_predict=2560, num_ctx=16384)

# サマリ 1500 字 + 最大 20 キャラ × 400 字 ≈ 9500 字 ≈ ~6000 tokens + 余裕
COMBINED_OPTIONS = make_llm_options(
    temperature=0.2,
    repeat_penalty=1.15,
    num_predict=16384,
    num_ctx=131072,
)

# ---------------------------------------------------------------------------
# プロンプトテンプレート
# ---------------------------------------------------------------------------

MAP_PROMPT = """次は小説『{book_name}』の本文の一部（{n} 分割の {i} 番目）です。
この部分の出来事を 400 字程度で要約してください。

要約に含めること:
- 誰が、何をしたか（主要キャラの発言・行動）
- 出来事の流れ（背景 → 主要な動き → 結果）
- 関係性の変化があれば明記

避けること:
- 描写の引用そのまま
- 全キャラを羅列するだけのもの

本文:
{text}

要約（400 字程度）:"""

REDUCE_PROMPT = """次は小説『{book_name}』の本文を時系列に分割要約したものです。
これを統合し、シリーズ俯瞰用の最終要約を {target} 字程度で書いてください。

最終要約に含めるべき内容:
- 主人公とその周囲の主要登場人物（誰が中心か）
- この巻における主要な出来事・対立・転機
- キャラクター関係性の変化（誰と誰の関係が動いたか）
- この巻のテーマや物語上の意味

避けること:
- 単なる場面の羅列
- 巻末の解説 / あとがきの引用

分割要約（時系列順に並んでいる）:
{summaries}

最終要約（{target} 字程度）:"""

SINGLE_PROMPT = """次は小説『{book_name}』の本文（連結ページ）です。
シリーズ俯瞰用の要約を {target} 字程度で書いてください。

要約に含めるべき内容:
- 主人公とその周囲の主要登場人物（誰が中心か）
- この巻における主要な出来事・対立・転機
- キャラクター関係性の変化
- この巻のテーマや物語上の意味

避けること:
- 単なる場面の羅列
- 巻末の解説 / あとがきの引用

本文:
{text}

要約（{target} 字程度）:"""

COMBINED_PROMPT = """次は小説『{book_name}』の本文（連結ページ）です。
以下の 3 セクションを指定のマーカー形式で出力してください。

[SUMMARY]
（{summary_target}字程度）
含めること: 主人公と主要登場人物 / この巻の主要な出来事・対立・転機 /
            キャラクター関係性の変化 / この巻のテーマや物語上の意味
避けること: 単なる場面の羅列 / 巻末解説・あとがきの引用

[CHARACTERS]
（重要度順に最大 {max_chars} 名、キャラ名のみ 1 行 1 名）

[CHARACTER_DETAIL:キャラ名]
（{char_target}字程度の 1 段落）
含めること: 役職・立場・他キャラとの関係 / この巻での主要な行動・選択・心情の動き /
            関係性の変化 / 印象的な台詞（あれば 1 つ引用）
避けること: 場面の単純な羅列 / 本文の長い引用

（[CHARACTER_DETAIL:キャラ名] を登場人物ぶんだけ繰り返す）

本文:
{text}

出力（マーカー [SUMMARY] / [CHARACTERS] / [CHARACTER_DETAIL:名前] から始めること）:"""

# ---------------------------------------------------------------------------
# 一括出力パーサ
# ---------------------------------------------------------------------------


def parse_combined_output(text: str) -> tuple[str, dict[str, str]]:
    """COMBINED_PROMPT への Qwen 応答から (書籍サマリ, {キャラ名: サマリ}) を抽出する。"""
    summary = ""
    char_summaries: dict[str, str] = {}

    m = re.search(
        r"\[SUMMARY\](.*?)(?=\[CHARACTERS\]|\[CHARACTER_DETAIL:|$)",
        text,
        re.DOTALL,
    )
    if m:
        summary = m.group(1).strip()

    for m in re.finditer(
        r"\[CHARACTER_DETAIL:([^\]]+)\](.*?)(?=\[CHARACTER_DETAIL:|$)",
        text,
        re.DOTALL,
    ):
        name = m.group(1).strip()
        detail = m.group(2).strip()
        if name and detail:
            char_summaries[name] = detail

    return summary, char_summaries
