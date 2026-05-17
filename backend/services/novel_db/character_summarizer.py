"""B-15 キャラクター辞典: 書籍 × キャラ単位の人物像サマリを Qwen で生成する。

`pages.main_characters` カラム（character_extractor が生成）を集計してキャラ名を
列挙し、各キャラについて「そのキャラが登場するページの本文だけ」を Qwen に投入。
キャラ視点の 1 段落（~400 字）の人物像を `book_characters.summary` に保存する。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.10 / B-15。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from config import NOVEL_DB_LLM_MODEL

from ._llm_backend import QWEN_BACKEND

# キャラ名は通常 5〜15 字、まれに敬称付きで 20 字程度。30 字超は誤抽出と判断。
_NAME_MAX_LEN = 30
# 1 キャラの page を全部連結したときの上限（Qwen num_ctx に余裕を持たせる）。
# 主要キャラでも全 page の半分以下に出るので、通常はこの上限に達しない。
_MAX_BODY_CHARS = 80_000

_PROMPT = """次は小説『{book_name}』から「{char_name}」が登場するページを page_no 順に集めた本文です。
この本（1 冊）における「{char_name}」の人物像を、1 段落（{target} 字程度）でまとめてください。

含めるべき要素:
- 役職・立場・他キャラとの関係（誰の誰か、どの組織の誰か）
- この巻における主要な行動・選択・心情の動き
- 他キャラとの関係性の変化があれば明記
- 印象的な台詞・象徴的なフレーズがあれば 1 つ引用

避けること:
- 場面の単純な羅列（「page X で Y した」の連続）
- 本文の長い引用
- 「彼 / 彼女」だけで言い換える曖昧化

本文（page_no 順、抜粋）:
{body}

『{book_name}』における「{char_name}」の人物像（{target} 字程度、1 段落）:"""

_TARGET_CHARS = 400

_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.15,
    "num_predict": 1024,   # 400 字 + 余裕
    # 主要キャラの body は 80k 字（_MAX_BODY_CHARS）まで取り得る ≒ ~50k tokens。
    # B-14 の llama-server は num_ctx=131072 起動なので余裕を持って 65536。
    "num_ctx": 65536,
}


@dataclass(frozen=True)
class CharacterStat:
    """書籍内 1 キャラの登場統計（サマリ生成前の集計値）。"""
    name: str
    first_page: int
    page_count: int


@dataclass(frozen=True)
class CharacterRow:
    """`book_characters` テーブルの 1 行（API 応答用）。"""
    name: str
    first_page: int
    page_count: int
    summary: str | None
    generated_at: str | None


def _parse_main_characters(raw: str | None) -> list[str]:
    """`pages.main_characters` のカンマ区切り文字列をキャラ名リストにする。

    character_extractor は「,」区切りで返すが、過去データの揺れに備えて
    「、」「・」も区切り扱い。空文字・極端に長い断片はスキップ。
    """
    if not raw:
        return []
    text = raw.replace("、", ",").replace("・", ",")
    out: list[str] = []
    for part in text.split(","):
        name = part.strip().strip("「」『』\"'.。 ")
        if not name or len(name) > _NAME_MAX_LEN:
            continue
        out.append(name)
    return out


def list_book_characters_in_db(
    conn: sqlite3.Connection,
    book_id: int,
) -> list[CharacterStat]:
    """書籍の `pages.main_characters` を集計してキャラ統計を返す。

    各キャラについて `first_page`（最初に登場した page_no）と `page_count`
    （登場ページ数）を計算。`page_count` 降順 → `first_page` 昇順でソート。
    """
    rows = conn.execute(
        """
        SELECT page_no, main_characters
        FROM pages
        WHERE book_id = ? AND main_characters IS NOT NULL AND main_characters <> ''
        ORDER BY page_no
        """,
        (book_id,),
    ).fetchall()

    stats: dict[str, dict[str, int]] = {}
    for page_no, raw in rows:
        for name in _parse_main_characters(raw):
            entry = stats.setdefault(name, {"first_page": page_no, "page_count": 0})
            entry["page_count"] += 1
            if page_no < entry["first_page"]:
                entry["first_page"] = page_no

    result = [
        CharacterStat(name=name, first_page=e["first_page"], page_count=e["page_count"])
        for name, e in stats.items()
    ]
    result.sort(key=lambda c: (-c.page_count, c.first_page, c.name))
    return result


def collect_character_pages(
    conn: sqlite3.Connection,
    book_id: int,
    char_name: str,
) -> list[tuple[int, str]]:
    """`main_characters` に `char_name` が含まれるページの (page_no, full_text) を返す。

    完全一致でフィルタする（MVP では表記揺れは考慮しない）。
    """
    rows = conn.execute(
        """
        SELECT page_no, full_text, main_characters
        FROM pages
        WHERE book_id = ? AND main_characters IS NOT NULL AND main_characters <> ''
            AND full_text IS NOT NULL AND full_text <> ''
        ORDER BY page_no
        """,
        (book_id,),
    ).fetchall()
    out: list[tuple[int, str]] = []
    for page_no, full_text, raw in rows:
        if char_name in _parse_main_characters(raw):
            out.append((page_no, full_text))
    return out


def summarize_character(
    book_name: str,
    char_name: str,
    pages: list[tuple[int, str]],
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    progress: Callable[[str], None] | None = None,
) -> str:
    """1 キャラ × 1 書籍の人物像サマリを Qwen で生成して返す（DB には書き込まない）。

    Raises:
        ValueError: pages が空。
        LLMError: Qwen 呼び出しに失敗。
    """
    if not pages:
        raise ValueError(f"no pages collected for character: {char_name}")

    # page_no 順に連結（過剰に長ければ末尾を切る）
    blocks: list[str] = []
    total_chars = 0
    for page_no, text in pages:
        block = f"[page {page_no}]\n{text}"
        if total_chars + len(block) > _MAX_BODY_CHARS:
            if progress is not None:
                progress(
                    f"    body limit {_MAX_BODY_CHARS:,} chars reached "
                    f"after page {page_no} (truncated)",
                )
            break
        blocks.append(block)
        total_chars += len(block) + 2  # 区切り改行分の概算

    body = "\n\n".join(blocks)
    prompt = _PROMPT.format(
        book_name=book_name, char_name=char_name, body=body, target=_TARGET_CHARS,
    )
    return QWEN_BACKEND.ask(prompt, model=model, options=_OPTIONS).strip()


def upsert_character(
    conn: sqlite3.Connection,
    book_id: int,
    stat: CharacterStat,
    summary: str | None,
) -> None:
    """`book_characters` を UPSERT する。

    summary が None / 空 のときは `summary` 列を NULL のまま保持
    （統計値の first_page / page_count だけ更新したいケース）。
    """
    has_summary = bool(summary and summary.strip())
    conn.execute(
        """
        INSERT INTO book_characters
            (book_id, name, summary, first_page, page_count, generated_at)
        VALUES (?, ?, ?, ?, ?, CASE WHEN ? THEN datetime('now', '+9 hours') ELSE NULL END)
        ON CONFLICT(book_id, name) DO UPDATE SET
            summary = CASE WHEN ? THEN excluded.summary ELSE book_characters.summary END,
            first_page = excluded.first_page,
            page_count = excluded.page_count,
            generated_at = CASE
                WHEN ? THEN excluded.generated_at
                ELSE book_characters.generated_at
            END
        """,
        (
            book_id, stat.name, summary if has_summary else None,
            stat.first_page, stat.page_count, has_summary,
            has_summary, has_summary,
        ),
    )
    conn.commit()


def list_characters(
    conn: sqlite3.Connection,
    book_id: int,
) -> list[CharacterRow]:
    """`book_characters` の保存済み行を返す（API 一覧用）。

    page_count 降順 → first_page 昇順 → name 昇順でソート。
    """
    rows = conn.execute(
        """
        SELECT name, first_page, page_count, summary, generated_at
        FROM book_characters
        WHERE book_id = ?
        ORDER BY page_count DESC, first_page ASC, name ASC
        """,
        (book_id,),
    ).fetchall()
    return [
        CharacterRow(
            name=name, first_page=fp, page_count=pc,
            summary=summary, generated_at=ga,
        )
        for name, fp, pc, summary, ga in rows
    ]


def get_character(
    conn: sqlite3.Connection,
    book_id: int,
    char_name: str,
) -> CharacterRow | None:
    """1 キャラの保存済み行を返す（API 詳細用）。未生成なら None。"""
    row = conn.execute(
        """
        SELECT name, first_page, page_count, summary, generated_at
        FROM book_characters
        WHERE book_id = ? AND name = ?
        """,
        (book_id, char_name),
    ).fetchone()
    if row is None:
        return None
    return CharacterRow(
        name=row[0], first_page=row[1], page_count=row[2],
        summary=row[3], generated_at=row[4],
    )


def top_scenes_for_character(
    conn: sqlite3.Connection,
    book_id: int,
    char_name: str,
    *,
    limit: int = 5,
) -> list[tuple[int, int]]:
    """キャラの主要シーン（page_no, char_count）を char_count 多い順 top N で返す。

    MVP の選定ロジック: `main_characters` に該当キャラを含む page のうち、
    `char_count` が多いページ（＝対話量・描写量が多い）を上位採用する。
    """
    rows = conn.execute(
        """
        SELECT page_no, char_count, main_characters
        FROM pages
        WHERE book_id = ? AND main_characters IS NOT NULL AND main_characters <> ''
        ORDER BY char_count DESC
        """,
        (book_id,),
    ).fetchall()
    out: list[tuple[int, int]] = []
    for page_no, char_count, raw in rows:
        if char_name in _parse_main_characters(raw):
            out.append((page_no, char_count))
            if len(out) >= limit:
                break
    return out
