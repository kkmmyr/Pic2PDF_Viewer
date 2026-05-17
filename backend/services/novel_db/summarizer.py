"""書籍 1 冊あたりの俯瞰要約（書籍サマリ）を Qwen で事前生成する。

`scope=all` / `scope=series` での概括的な質問（「シリーズ全体のテーマは？」等）への
回答品質を引き上げるため、各冊を 1500 字程度に要約して `books.summary` に保存する。
QA 時に検索ヒットページのコンテキストに加えてサマリ群をプロンプト先頭に追加する。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.7 / §7.2 を参照。

実装方針（B-6 検証で 1-shot 経路が主流に切替、2026-05-10）:
- 1 冊の本文（min_chars / body_page_margin で前付け・後付けを除外）をページ単位で連結
- 通常は 1-shot で Qwen（num_ctx=131072）に丸ごと渡す
- 1-shot で収まらない異常に大きな本文（>200,000 字）の場合のみ map-reduce にフォールバック

プロンプトテンプレート・LLM オプション・パーサは `_prompts.py` に一元管理している。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable

from config import (
    NOVEL_DB_BODY_PAGE_MARGIN,
    NOVEL_DB_LLM_MODEL,
    NOVEL_DB_MIN_BODY_CHARS,
)

from ._llm_backend import QWEN_BACKEND
from ._prompts import (
    CHAR_SUMMARY_TARGET_CHARS,
    COMBINED_MAX_CHARACTERS,
    COMBINED_OPTIONS,
    COMBINED_PROMPT,
    FINAL_SUMMARY_TARGET_CHARS,
    MAP_CHUNK_TARGET_CHARS,
    MAP_MAX_CHUNKS,
    MAP_OPTIONS,
    MAP_PROMPT,
    ONE_SHOT_MAX_BODY_CHARS,
    ONE_SHOT_OPTIONS,
    REDUCE_OPTIONS,
    REDUCE_PROMPT,
    SINGLE_PROMPT,
    parse_combined_output,
)
from .embedder import embed_batch
from .lance_store import get_summaries_table

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
    """1 冊の本文から書籍サマリを生成して返す（DB には書き込まない）。

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
        "SELECT id, page_count FROM books WHERE name = ?", (book_name,),
    ).fetchone()
    if book_row is None:
        raise ValueError(f"book not found: {book_name}")
    book_id, page_count = book_row

    body_text = _load_body_text(
        conn, book_id, page_count,
        min_chars=min_chars, body_page_margin=body_page_margin,
    )
    if not body_text.strip():
        raise ValueError(f"book has no body content: {book_name}")

    if len(body_text) <= ONE_SHOT_MAX_BODY_CHARS:
        _log(
            progress,
            f"  body chars={len(body_text):,} → one-shot (num_ctx={ONE_SHOT_OPTIONS['num_ctx']:,})",
        )
        prompt = SINGLE_PROMPT.format(
            book_name=book_name, text=body_text,
            target=FINAL_SUMMARY_TARGET_CHARS,
        )
        return QWEN_BACKEND.ask(prompt, model=model, options=ONE_SHOT_OPTIONS).strip()

    return _run_map_reduce_summary(book_name, body_text, model=model, progress=progress)


def summarize_book_with_characters(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    min_chars: int = NOVEL_DB_MIN_BODY_CHARS,
    body_page_margin: int = NOVEL_DB_BODY_PAGE_MARGIN,
    max_characters: int = COMBINED_MAX_CHARACTERS,
    progress: Callable[[str], None] | None = None,
) -> tuple[str, dict[str, str]]:
    """書籍サマリとキャラクター辞典を 1 回の Qwen 呼び出しで生成する。

    Returns:
        (book_summary, {char_name: char_summary})
        本文が ONE_SHOT_MAX_BODY_CHARS を超える場合はサマリのみ生成し、
        キャラクター辞典は空 dict を返す（map-reduce フォールバック）。

    Raises:
        ValueError: 書籍が DB に存在しない、または本文が空
        LLMError: Qwen 呼び出し失敗
    """
    book_row = conn.execute(
        "SELECT id, page_count FROM books WHERE name = ?", (book_name,),
    ).fetchone()
    if book_row is None:
        raise ValueError(f"book not found: {book_name}")
    book_id, page_count = book_row

    body_text = _load_body_text(
        conn, book_id, page_count,
        min_chars=min_chars, body_page_margin=body_page_margin,
    )
    if not body_text.strip():
        raise ValueError(f"book has no body content: {book_name}")

    if len(body_text) > ONE_SHOT_MAX_BODY_CHARS:
        _log(
            progress,
            f"  body chars={len(body_text):,} → too large for combined call; summary-only (map-reduce)",
        )
        summary = _run_map_reduce_summary(book_name, body_text, model=model, progress=progress)
        return summary, {}

    _log(
        progress,
        f"  body chars={len(body_text):,} → combined one-shot "
        f"(summary + up to {max_characters} characters, num_ctx={COMBINED_OPTIONS['num_ctx']:,})",
    )
    prompt = COMBINED_PROMPT.format(
        book_name=book_name,
        text=body_text,
        summary_target=FINAL_SUMMARY_TARGET_CHARS,
        char_target=CHAR_SUMMARY_TARGET_CHARS,
        max_chars=max_characters,
    )
    response = QWEN_BACKEND.ask(prompt, model=model, options=COMBINED_OPTIONS).strip()
    summary, char_summaries = parse_combined_output(response)

    if not summary:
        _log(progress, "  warning: [SUMMARY] marker not found; using response head as summary")
        summary = response[: FINAL_SUMMARY_TARGET_CHARS * 2]

    _log(progress, f"  done: summary={len(summary)} chars, {len(char_summaries)} characters")
    return summary, char_summaries


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
        "UPDATE books SET summary = ?, summary_generated_at = datetime('now', '+9 hours') "
        "WHERE id = ?",
        (summary, book_id),
    )
    _index_summary_vector(conn, book_id, summary)
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
        f"SELECT name, summary FROM books "  # noqa: S608
        f"WHERE name IN ({placeholders}) AND summary IS NOT NULL AND summary <> ''",
        book_names,
    ).fetchall()
    return {name: summary for name, summary in rows}


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------

def _load_body_text(
    conn: sqlite3.Connection,
    book_id: int,
    page_count: int,
    *,
    min_chars: int,
    body_page_margin: int,
) -> str:
    """書籍の本文テキストをページ順に連結して返す（前付け・後付け除外）。"""
    rows = conn.execute(
        """
        SELECT page_no, full_text
        FROM pages
        WHERE book_id = ?
          AND char_count >= ?
          AND page_no > ?
          AND page_no <= ?
        ORDER BY page_no
        """,
        (book_id, min_chars, body_page_margin, page_count - body_page_margin),
    ).fetchall()
    return "\n".join(text for _, text in rows if text)


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
    summaries_block = "\n\n".join(
        f"[{i}/{len(intermediates)}]\n{s}" for i, s in enumerate(intermediates, 1)
    )
    prompt = REDUCE_PROMPT.format(
        book_name=book_name, summaries=summaries_block,
        target=FINAL_SUMMARY_TARGET_CHARS,
    )
    return QWEN_BACKEND.ask(prompt, model=model, options=REDUCE_OPTIONS).strip()


def _index_summary_vector(
    conn: sqlite3.Connection,
    book_id: int,
    summary: str,
) -> None:
    """書籍サマリを bge-m3 で embedding し、LanceDB summaries テーブルに upsert する。"""
    try:
        emb = embed_batch([summary])[0]
    except Exception as e:  # noqa: BLE001
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "Failed to index summary vector for book_id=%s: %s", book_id, e,
        )
        return
    book_name_row = conn.execute("SELECT name FROM books WHERE id = ?", (book_id,)).fetchone()
    book_name = book_name_row[0] if book_name_row else ""
    table = get_summaries_table()
    table.delete(f"book_id = {book_id}")
    table.add([{"book_id": book_id, "book_name": book_name, "embedding": emb}])


def _log(cb: Callable[[str], None] | None, msg: str) -> None:
    if cb is not None:
        cb(msg)
