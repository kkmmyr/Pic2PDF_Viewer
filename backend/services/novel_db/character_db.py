"""B-15 キャラクター辞典: novel.db の book_characters テーブルに対する DB アクセス層。

LLM による人物像サマリ生成ロジックは character_summarizer.py を参照。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

# キャラ名は通常 5〜15 字、まれに敬称付きで 20 字程度。30 字超は誤抽出と判断。
_NAME_MAX_LEN = 30


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
