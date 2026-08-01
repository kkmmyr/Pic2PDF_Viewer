"""書籍 1 冊あたりの俯瞰要約（書籍サマリ）を Qwen で事前生成する。

`scope=all` / `scope=series` での概括的な質問（「シリーズ全体のテーマは？」等）への
回答品質を引き上げるため、各冊を必要情報と可読性優先の可変長で要約し
`books.summary` に保存する。
QA 時に検索ヒットページのコンテキストに加えてサマリ群をプロンプト先頭に追加する。

詳細は docs/design/詳細設計/機能別/小説RAG_パイプライン設計.md §4 / docs/design/詳細設計/機能別/小説RAG_検索QA設計.md §4 を参照。

実装方針（2026-07-28 品質優先パイプライン）:
- 本文をページ番号付きで事実表へ変換する
- 書籍要約と各人物説明を事実表から別々に生成する
- 別の編集プロンプトで自然さを校正し、機械ゲートを通った候補だけを返す
- 人物本文がcontext上限を超える場合は、先頭切りではなく全登場範囲から選ぶ

プロンプトテンプレート・LLM オプション・パーサは `_prompts.py` に一元管理している。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from config import (
    NOVEL_DB_BODY_PAGE_MARGIN,
    NOVEL_DB_LLM_MODEL,
    NOVEL_DB_MIN_BODY_CHARS,
    NOVEL_DB_VERIFIER_MODEL,
)

from ._llm_backend import QWEN_BACKEND, VERIFIER_BACKEND
from ._prompts import (
    COMBINED_MAX_CHARACTERS,
    MAP_CHUNK_TARGET_CHARS,
    MAP_MAX_CHUNKS,
    MAP_OPTIONS,
    MAP_PROMPT,
    REDUCE_OPTIONS,
    REDUCE_PROMPT,
)
from .embedder import embed_batch
from .lance_store import get_summaries_table
from .prose_pipeline import (
    extract_fact_sheet,
    write_and_edit_catalog_summary,
    write_and_edit_characters,
    write_and_edit_summary,
)
from .summary_grounding import verify_summary_grounding

# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def summarize_book(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    min_chars: int = NOVEL_DB_MIN_BODY_CHARS,
    body_page_margin: int = NOVEL_DB_BODY_PAGE_MARGIN,
    progress: Callable[[str], None] | None = None,
) -> str:
    """1 冊の本文から書籍サマリを生成して返す。

    公開用の`books.summary`は更新しない。再実行用の事実抽出チェックポイントだけは
    ブロックごとに`fact_extraction_blocks`へ保存する。

    Args:
        conn: novel.db の接続
        book_name: 対象書籍名（`books.name`）
        model: 使用する Qwen モデル
        min_chars: ページ採用の char_count 閾値（薄いページ除外）
        body_page_margin: 各書籍の先頭・末尾何ページを除外するか
        progress: 進捗ログ用コールバック（CLI から進捗表示する用）

    Returns:
        生成された要約テキスト

    Raises:
        ValueError: 対象書籍が DB に無い、または本文が空
        QwenError: Qwen 呼び出しに失敗
    """
    book_row = conn.execute(
        "SELECT id, page_count FROM books WHERE name = ?",
        (book_name,),
    ).fetchone()
    if book_row is None:
        raise ValueError(f"book not found: {book_name}")
    book_id, page_count = book_row
    canonical_character_names = _load_published_character_names(conn, book_id)

    body_pages = _load_body_pages(
        conn,
        book_id,
        page_count,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )
    if not body_pages:
        raise ValueError(f"book has no body content: {book_name}")

    fact_sheet = extract_fact_sheet(
        conn,
        book_id,
        book_name,
        body_pages,
        model=model,
        progress=progress,
        canonical_character_names=canonical_character_names,
    )
    summary = write_and_edit_summary(
        book_name,
        fact_sheet,
        model=model,
        progress=progress,
    )
    _log(progress, "  verifying summary grounding and fact coverage")
    verify_summary_grounding(
        conn,
        book_id=book_id,
        book_name=book_name,
        summary=summary,
        fact_sheet=fact_sheet,
        writer_model=model,
        verifier_backend=VERIFIER_BACKEND,
        verifier_model=NOVEL_DB_VERIFIER_MODEL or model,
    )
    return summary


def summarize_book_with_characters(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    min_chars: int = NOVEL_DB_MIN_BODY_CHARS,
    body_page_margin: int = NOVEL_DB_BODY_PAGE_MARGIN,
    max_characters: int = COMBINED_MAX_CHARACTERS,
    progress: Callable[[str], None] | None = None,
) -> tuple[str, str, dict[str, str]]:
    """詳細あらすじ、一覧向け短縮要約、人物辞典を別々に生成する。

    公開用テーブルは更新せず、事実抽出チェックポイントだけを保存する。

    Returns:
        (detailed_summary, catalog_summary, {char_name: char_summary})

    Raises:
        ValueError: 書籍が DB に存在しない、または本文が空
        LLMError: Qwen 呼び出し失敗
    """
    book_row = conn.execute(
        "SELECT id, page_count FROM books WHERE name = ?",
        (book_name,),
    ).fetchone()
    if book_row is None:
        raise ValueError(f"book not found: {book_name}")
    book_id, page_count = book_row
    canonical_character_names = _load_published_character_names(conn, book_id)

    body_pages = _load_body_pages(
        conn,
        book_id,
        page_count,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )
    if not body_pages:
        raise ValueError(f"book has no body content: {book_name}")

    fact_sheet = extract_fact_sheet(
        conn,
        book_id,
        book_name,
        body_pages,
        model=model,
        progress=progress,
        canonical_character_names=canonical_character_names,
    )
    summary = write_and_edit_summary(
        book_name=book_name,
        fact_sheet=fact_sheet,
        model=model,
        progress=progress,
    )
    _log(progress, "  verifying summary grounding and fact coverage")
    verify_summary_grounding(
        conn,
        book_id=book_id,
        book_name=book_name,
        summary=summary,
        fact_sheet=fact_sheet,
        writer_model=model,
        verifier_backend=VERIFIER_BACKEND,
        verifier_model=NOVEL_DB_VERIFIER_MODEL or model,
        content_type="detailed",
        coverage_required=True,
    )
    catalog_summary = write_and_edit_catalog_summary(
        book_name,
        fact_sheet,
        summary,
        model=model,
        progress=progress,
    )
    _log(progress, "  verifying catalog summary claims")
    verify_summary_grounding(
        conn,
        book_id=book_id,
        book_name=book_name,
        summary=catalog_summary,
        fact_sheet=fact_sheet,
        writer_model=model,
        verifier_backend=VERIFIER_BACKEND,
        verifier_model=NOVEL_DB_VERIFIER_MODEL or model,
        content_type="catalog",
        coverage_required=False,
    )
    char_summaries = write_and_edit_characters(
        conn,
        book_id,
        book_name,
        fact_sheet,
        model=model,
        max_characters=max_characters,
        progress=progress,
    )

    _log(
        progress,
        f"  done: detailed={len(summary)} chars, catalog={len(catalog_summary)} chars, "
        f"{len(char_summaries)} characters",
    )
    return summary, catalog_summary, char_summaries


def _load_published_character_names(conn: sqlite3.Connection, book_id: int) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM book_characters WHERE book_id = ? ORDER BY id",
            (book_id,),
        ).fetchall()
    ]


def update_book_summary(
    conn: sqlite3.Connection,
    book_name: str,
    summary: str,
) -> None:
    """生成済みのサマリを `books.summary` に保存し、`book_summaries_vec` も更新する。

    B-8: サマリの embedding を取り、検索インデックスに登録する。失敗（embedder
    タイムアウト等）時は `books.summary` だけ更新して vec 側は次回 `--redo` を待つ
    （後方互換: vec が無くても summary は使える）。
    """
    row = conn.execute("SELECT id FROM books WHERE name = ?", (book_name,)).fetchone()
    if row is None:
        raise ValueError(f"book not found: {book_name}")
    book_id = row[0]

    conn.execute(
        "UPDATE books SET summary = ?, summary_generated_at = datetime('now', '+9 hours') WHERE id = ?",
        (summary, book_id),
    )
    index_book_summary(conn, book_id, summary)
    conn.commit()


def load_summaries_for_books(
    conn: sqlite3.Connection,
    book_names: list[str],
) -> dict[str, str]:
    """指定された書籍の summary を一括取得する。NULL/空のものは含めない。"""
    if not book_names:
        return {}
    placeholders = ",".join("?" * len(book_names))
    rows = conn.execute(
        f"SELECT name, summary FROM books WHERE name IN ({placeholders}) AND summary IS NOT NULL AND summary <> ''",
        book_names,
    ).fetchall()
    return {name: summary for name, summary in rows}


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _load_body_pages(
    conn: sqlite3.Connection,
    book_id: int,
    page_count: int,
    *,
    min_chars: int,
    body_page_margin: int,
) -> list[tuple[int, str]]:
    """Load eligible body pages in reading order with page evidence intact."""
    rows = conn.execute(
        """
        SELECT page_no, full_text
        FROM pages
        WHERE book_id = ?
          AND index_eligible = 1
          AND char_count >= ?
          AND page_no > ?
          AND page_no <= ?
        ORDER BY page_no
        """,
        (book_id, min_chars, body_page_margin, page_count - body_page_margin),
    ).fetchall()
    return [(int(page_no), str(text)) for page_no, text in rows if text]


def _load_body_text(
    conn: sqlite3.Connection,
    book_id: int,
    page_count: int,
    *,
    min_chars: int,
    body_page_margin: int,
) -> str:
    """書籍の本文テキストをページ順に連結して返す（前付け・後付け除外）。"""
    pages = _load_body_pages(
        conn,
        book_id,
        page_count,
        min_chars=min_chars,
        body_page_margin=body_page_margin,
    )
    return "\n".join(text for _, text in pages)


def _chunk_for_map(text: str) -> list[str]:
    """テキストを map フェーズ用のチャンクに分割する（チャンク数固定・改行境界優先）。"""
    if len(text) <= MAP_CHUNK_TARGET_CHARS:
        return [text]

    n_chunks = min(
        MAP_MAX_CHUNKS,
        (len(text) + MAP_CHUNK_TARGET_CHARS - 1) // MAP_CHUNK_TARGET_CHARS,
    )
    target = len(text) // n_chunks

    chunks: list[str] = []
    cursor = 0
    for i in range(n_chunks - 1):
        boundary_min = cursor + target
        nl = text.find("\n", boundary_min)
        if nl == -1 or nl >= len(text) - 1:
            chunks.append(text[cursor:])
            return chunks
        chunks.append(text[cursor:nl])
        cursor = nl + 1
        _ = i
    chunks.append(text[cursor:])
    return chunks


def _run_map_reduce_summary(
    book_name: str,
    body_text: str,
    *,
    model: str,
    progress: Callable[[str], None] | None = None,
) -> str:
    """map-reduce で書籍サマリを生成する（>200,000 字の本文用フォールバック）。"""
    chunks = _chunk_for_map(body_text)
    _log(
        progress,
        f"  body chars={len(body_text):,} → map-reduce ({len(chunks)} chunks, 超過のため)",
    )
    intermediates: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        _log(progress, f"  map {i}/{len(chunks)} (chars={len(chunk):,})...")
        prompt = MAP_PROMPT.format(book_name=book_name, i=i, n=len(chunks), text=chunk)
        intermediates.append(QWEN_BACKEND.ask(prompt, model=model, options=MAP_OPTIONS).strip())

    _log(progress, f"  reduce ({sum(len(s) for s in intermediates):,} chars)...")
    summaries_block = "\n\n".join(f"[{i}/{len(intermediates)}]\n{s}" for i, s in enumerate(intermediates, 1))
    prompt = REDUCE_PROMPT.format(
        book_name=book_name,
        summaries=summaries_block,
    )
    return QWEN_BACKEND.ask(prompt, model=model, options=REDUCE_OPTIONS).strip()


def index_book_summary(
    conn: sqlite3.Connection,
    book_id: int,
    summary: str,
    *,
    raise_on_error: bool = False,
) -> None:
    """書籍サマリを bge-m3 で embedding し、LanceDB summaries テーブルに upsert する。

    通常ビルドではSQLite本文の確定を優先して失敗を警告に留める。復元監査など、
    クロスストア同期を完了条件にする呼び出し元は ``raise_on_error=True`` を指定する。
    """
    try:
        emb = embed_batch([summary])[0]
        book_name_row = conn.execute(
            "SELECT name FROM books WHERE id = ?",
            (book_id,),
        ).fetchone()
        book_name = book_name_row[0] if book_name_row else ""
        table = get_summaries_table()
        table.delete(f"book_id = {book_id}")
        table.add([{"book_id": book_id, "book_name": book_name, "embedding": emb}])
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to index summary vector for book_id=%s: %s",
            book_id,
            e,
        )
        if raise_on_error:
            raise


def _log(cb: Callable[[str], None] | None, msg: str) -> None:
    if cb is not None:
        cb(msg)
