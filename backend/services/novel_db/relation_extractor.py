"""C-12: キャラクタ関係グラフ生成。

共起カウントでエッジ重みを算出し、Qwen で関係タイプラベルを抽出する。
抽出結果は character_relations テーブルに UPSERT する。

詳細は docs/archive/要件/C12_キャラクタ関係グラフ_要件.md。
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from itertools import combinations

from local_llm import LLMError

from config import NOVEL_DB_LLM_MODEL
from utils.dt import JST

from .character_names import parse_character_names
from .llm_options import make_llm_options
from .llm_provider import NovelLlmProvider, get_llm_provider
from .relation_parser import parse_relation_response

_RELATION_PROMPT = """以下は小説『{book_name}』のキャラクター辞典サマリのリストです。
各キャラクターのサマリを読み、登場人物間の関係タイプを抽出してください。

キャラクター一覧:
{characters}

出力形式（JSON 配列）:
[
  {{"char_a": "キャラ名A", "char_b": "キャラ名B", "relation": "関係タイプ（例: 友人・師弟・敵対・家族・恋愛・同僚）"}},
  ...
]

注意:
- 明確な関係が読み取れるペアのみ出力する（推測しない）
- char_a / char_b の順序は問わない（一方向のみ出力）
- relation は簡潔な日本語で（10 字以内推奨）

JSON のみ出力（前置き・説明不要）:"""

_OPTIONS = make_llm_options(temperature=0.1, num_predict=2048, num_ctx=16384)


def count_cooccurrences(
    conn: sqlite3.Connection,
    book_id: int,
) -> Counter[tuple[str, str]]:
    """同一ページ内の共起回数を返す（ペアはアルファベット順で正規化）。"""
    rows = conn.execute(
        "SELECT main_characters FROM pages WHERE book_id = ? AND index_eligible = 1 "
        "AND main_characters IS NOT NULL AND main_characters <> ''",
        (book_id,),
    ).fetchall()
    counter: Counter[tuple[str, str]] = Counter()
    for (raw,) in rows:
        names = parse_character_names(raw)
        for a, b in combinations(names, 2):
            key = (a, b) if a < b else (b, a)
            counter[key] += 1
    return counter


def extract_relations_with_qwen(
    book_name: str,
    character_summaries: list[tuple[str, str]],
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    provider: NovelLlmProvider | None = None,
) -> list[tuple[str, str, str]]:
    """Qwen でキャラサマリから関係タイプを抽出する。

    Args:
        character_summaries: [(char_name, summary_text), ...]

    Returns:
        [(char_a, char_b, relation_type), ...] — Qwen が認識したペアのみ
    """
    if not character_summaries:
        return []

    chars_text = "\n".join(f"【{name}】\n{summary}" for name, summary in character_summaries if summary)
    if not chars_text.strip():
        return []

    prompt = _RELATION_PROMPT.format(book_name=book_name, characters=chars_text)
    try:
        raw = (provider or get_llm_provider()).qwen.ask(prompt, model=model, options=_OPTIONS).strip()
    except LLMError:
        return []

    return parse_relation_response(raw)


def store_relations(
    conn: sqlite3.Connection,
    book_id: int,
    series_id: str,
    cooccurrences: Counter[tuple[str, str]],
    qwen_relations: list[tuple[str, str, str]],
) -> int:
    """character_relations に REPLACE INSERT する。既存データは書き直し。

    Returns:
        挿入した行数
    """
    now = datetime.now(JST).isoformat()

    # 既存データを削除して書き直し
    conn.execute(
        "DELETE FROM character_relations WHERE book_id = ?",
        (book_id,),
    )

    # Qwen ラベルをキーにまとめる
    qwen_map: dict[tuple[str, str], str] = {}
    for a, b, rel in qwen_relations:
        key = (a, b) if a < b else (b, a)
        qwen_map[key] = rel

    inserted = 0
    for (char_a, char_b), weight in cooccurrences.items():
        relation_type = qwen_map.get((char_a, char_b))
        conn.execute(
            "INSERT INTO character_relations "
            "(series_id, book_id, char_a, char_b, relation_type, weight, generated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (series_id, book_id, char_a, char_b, relation_type, float(weight), now),
        )
        inserted += 1

    # 共起にないが Qwen が認識したペアも追加（weight=0）
    cooc_keys = set(cooccurrences.keys())
    for (char_a, char_b), rel in qwen_map.items():
        if (char_a, char_b) not in cooc_keys:
            conn.execute(
                "INSERT INTO character_relations "
                "(series_id, book_id, char_a, char_b, relation_type, weight, generated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (series_id, book_id, char_a, char_b, rel, 0.0, now),
            )
            inserted += 1

    conn.commit()
    return inserted


def generate_book_relations(
    conn: sqlite3.Connection,
    book_name: str,
    series_id: str,
    *,
    detail_callback: Callable[[str], None] | None = None,
    provider: NovelLlmProvider | None = None,
) -> int:
    """1 冊分の character_relations を生成する。

    Returns:
        挿入した関係ペア数
    """

    def _detail(msg: str) -> None:
        if detail_callback:
            detail_callback(msg)

    row = conn.execute("SELECT id FROM books WHERE name = ?", (book_name,)).fetchone()
    if row is None:
        raise ValueError(f"book not found: {book_name}")
    book_id: int = row[0]

    _detail("共起カウント中...")
    cooc = count_cooccurrences(conn, book_id)
    _detail(f"共起ペア {len(cooc)} 件")

    # キャラサマリを取得して Qwen 抽出
    char_rows = conn.execute(
        "SELECT name, summary FROM book_characters WHERE book_id = ? AND summary IS NOT NULL",
        (book_id,),
    ).fetchall()
    _detail(f"Qwen 関係抽出（キャラ {len(char_rows)} 件）...")
    qwen_rels = extract_relations_with_qwen(book_name, char_rows, provider=provider)
    _detail(f"Qwen 抽出ペア {len(qwen_rels)} 件")

    count = store_relations(conn, book_id, series_id, cooc, qwen_rels)
    _detail(f"character_relations に {count} 件を保存")
    return count
