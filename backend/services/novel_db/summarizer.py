"""書籍 1 冊あたりの俯瞰要約（書籍サマリ）を Qwen で事前生成する。

`scope=all` / `scope=series` での概括的な質問（「シリーズ全体のテーマは？」等）への
回答品質を引き上げるため、各冊を 1500 字程度に要約して `books.summary` に保存する。
QA 時に検索ヒットページのコンテキストに加えてサマリ群をプロンプト先頭に追加する。

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.7 / §7.2 を参照。
ADR-0007 とは独立した品質改善（B-5）。

実装方針（B-6 検証で 1-shot 経路が主流に切替、2026-05-10）:
- 1 冊の本文（min_chars / body_page_margin で前付け・後付けを除外）をページ単位で連結
- 通常は 1-shot で Qwen（num_ctx=131072）に丸ごと渡す。検証で OOM せず prompt 70k tokens
  を完全に読み込んで done_reason='stop' で完走することを確認済み
- 1-shot で収まらない異常に大きな本文（>200,000 字 ≒ ~125k tokens）の場合のみ
  map-reduce にフォールバック
    - map: 各チャンクを 400 字程度に要約
    - reduce: 全 map 結果を最終 1500 字サマリに統合
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable

from config import (
    NOVEL_DB_BODY_PAGE_MARGIN,
    NOVEL_DB_LLM_MODEL,
    NOVEL_DB_MIN_BODY_CHARS,
)

from ._llm_backend import build_qwen_backend
from .embedder import embed_batch, serialize_f32

# プロセス起動時に Backend を作る。Backend は stateless なので使い回しで OK。
_BACKEND = build_qwen_backend()

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

# 1-shot 経路で許容する最大本文文字数。これを超えたら map-reduce にフォールバック。
# Qwen は ~1.6 chars/token なので 200,000 字 ≒ 125k tokens。num_ctx=131072 でぎりぎり。
_ONE_SHOT_MAX_BODY_CHARS = 200_000

# map フェーズの 1 チャンクあたりの目標文字数
# Qwen num_ctx=16384 トークンは日本語で ~10000-13000 字程度の入力に相当
# プロンプト・出力分を考慮して入力は ~20000 字までは詰めて投げる（要トークン化超過時は分割）
_MAP_CHUNK_TARGET_CHARS = 20000

# map フェーズの最大チャンク数（過大な書籍でも 8 チャンク以内に抑える）
_MAP_MAX_CHUNKS = 8

# reduce フェーズの目標サマリ長
_FINAL_SUMMARY_TARGET_CHARS = 1500

# Qwen LLM オプション
_ONE_SHOT_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.15,
    "num_predict": 2560,   # 1500 字サマリ + 余裕
    "num_ctx": 131072,     # B-6 検証で 70k tokens 完走を確認（2026-05-10）
}
_MAP_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.15,
    "num_predict": 768,    # 1 チャンクあたり 400 字程度の要約 + 余裕
    "num_ctx": 16384,
}
_REDUCE_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.15,
    "num_predict": 2560,   # 最終 1500 字サマリ + 余裕
    "num_ctx": 16384,
}

# 一括生成（書籍サマリ + キャラクター辞典）の定数
_CHAR_SUMMARY_TARGET_CHARS = 400
_COMBINED_MAX_CHARACTERS = 20  # 一括出力で扱う最大キャラクター数

_COMBINED_OPTIONS = {
    "temperature": 0.2,
    "repeat_penalty": 1.15,
    # サマリ 1500 字 + 最大 20 キャラ × 400 字 ≈ 9500 字 ≈ ~6000 tokens + 余裕
    "num_predict": 16384,
    "num_ctx": 131072,
}

_COMBINED_PROMPT = """次は小説『{book_name}』の本文（連結ページ）です。
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

# プロンプトテンプレート
_MAP_PROMPT = """次は小説『{book_name}』の本文の一部（{n} 分割の {i} 番目）です。
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

_REDUCE_PROMPT = """次は小説『{book_name}』の本文を時系列に分割要約したものです。
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

_SINGLE_PROMPT = """次は小説『{book_name}』の本文（連結ページ）です。
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

    if len(body_text) <= _ONE_SHOT_MAX_BODY_CHARS:
        # 通常経路: num_ctx=131072 で 1 冊丸ごと 1-shot 要約
        # （B-6 検証で 70k tokens 完走を確認、2026-05-10）
        _log(
            progress,
            f"  body chars={len(body_text):,} → one-shot (num_ctx={_ONE_SHOT_OPTIONS['num_ctx']:,})",
        )
        prompt = _SINGLE_PROMPT.format(
            book_name=book_name, text=body_text,
            target=_FINAL_SUMMARY_TARGET_CHARS,
        )
        return _BACKEND.ask(prompt, model=model, options=_ONE_SHOT_OPTIONS).strip()

    return _run_map_reduce_summary(book_name, body_text, model=model, progress=progress)


def summarize_book_with_characters(
    conn: sqlite3.Connection,
    book_name: str,
    *,
    model: str = NOVEL_DB_LLM_MODEL,
    min_chars: int = NOVEL_DB_MIN_BODY_CHARS,
    body_page_margin: int = NOVEL_DB_BODY_PAGE_MARGIN,
    max_characters: int = _COMBINED_MAX_CHARACTERS,
    progress: Callable[[str], None] | None = None,
) -> tuple[str, dict[str, str]]:
    """書籍サマリとキャラクター辞典を 1 回の Qwen 呼び出しで生成する。

    Returns:
        (book_summary, {char_name: char_summary})
        本文が _ONE_SHOT_MAX_BODY_CHARS を超える場合はサマリのみ生成し、
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

    if len(body_text) > _ONE_SHOT_MAX_BODY_CHARS:
        _log(
            progress,
            f"  body chars={len(body_text):,} → too large for combined call; summary-only (map-reduce)",
        )
        summary = _run_map_reduce_summary(book_name, body_text, model=model, progress=progress)
        return summary, {}

    _log(
        progress,
        f"  body chars={len(body_text):,} → combined one-shot "
        f"(summary + up to {max_characters} characters, num_ctx={_COMBINED_OPTIONS['num_ctx']:,})",
    )
    prompt = _COMBINED_PROMPT.format(
        book_name=book_name,
        text=body_text,
        summary_target=_FINAL_SUMMARY_TARGET_CHARS,
        char_target=_CHAR_SUMMARY_TARGET_CHARS,
        max_chars=max_characters,
    )
    response = _BACKEND.ask(prompt, model=model, options=_COMBINED_OPTIONS).strip()
    summary, char_summaries = _parse_combined_output(response)

    if not summary:
        _log(progress, "  warning: [SUMMARY] marker not found; using response head as summary")
        summary = response[: _FINAL_SUMMARY_TARGET_CHARS * 2]

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
        "UPDATE books SET summary = ?, summary_generated_at = datetime('now') "
        "WHERE id = ?",
        (summary, book_id),
    )
    _index_summary_vector(conn, book_id, summary)
    conn.commit()


def _index_summary_vector(
    conn: sqlite3.Connection,
    book_id: int,
    summary: str,
) -> None:
    """書籍サマリを bge-m3 で embedding し、`book_summaries_vec` に upsert する。

    既に同 rowid のレコードが存在する場合は DELETE → INSERT で置き換える
    （vec0 仮想テーブルは UPSERT 構文をサポートしないため）。
    """
    try:
        emb = embed_batch([summary])[0]
    except Exception as e:  # noqa: BLE001
        # embedder タイムアウト・接続失敗等は検索インデックス側の更新だけスキップ
        # （summary 本体は保存済み。ベクトルは次回 --redo で再構築される）
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "Failed to index summary vector for book_id=%s: %s", book_id, e,
        )
        return
    conn.execute("DELETE FROM book_summaries_vec WHERE rowid = ?", (book_id,))
    conn.execute(
        "INSERT INTO book_summaries_vec (rowid, embedding) VALUES (?, ?)",
        (book_id, serialize_f32(emb)),
    )


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
    """テキストを map フェーズ用のチャンクに分割する。

    各チャンクが概ね `_MAP_CHUNK_TARGET_CHARS` 字以下、かつチャンク数が
    `_MAP_MAX_CHUNKS` 以内に収まるよう、改行境界優先で切る（チャンク数固定方式）。
    """
    if len(text) <= _MAP_CHUNK_TARGET_CHARS:
        return [text]

    # 必要なチャンク数を _MAP_MAX_CHUNKS 以内に抑えつつ、各チャンクをほぼ均等にする
    n_chunks = min(
        _MAP_MAX_CHUNKS,
        (len(text) + _MAP_CHUNK_TARGET_CHARS - 1) // _MAP_CHUNK_TARGET_CHARS,
    )
    target = len(text) // n_chunks

    chunks: list[str] = []
    cursor = 0
    for i in range(n_chunks - 1):
        # target 位置以降の最初の改行を探し、そこをチャンク境界にする
        boundary_min = cursor + target
        nl = text.find("\n", boundary_min)
        if nl == -1 or nl >= len(text) - 1:
            # 後段のチャンクが取れない → 残り全部を最後のチャンクに
            chunks.append(text[cursor:])
            return chunks
        chunks.append(text[cursor:nl])
        cursor = nl + 1
        _ = i  # silence flake8 if any
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
        prompt = _MAP_PROMPT.format(book_name=book_name, i=i, n=len(chunks), text=chunk)
        intermediates.append(_BACKEND.ask(prompt, model=model, options=_MAP_OPTIONS).strip())

    _log(progress, f"  reduce ({sum(len(s) for s in intermediates):,} chars)...")
    summaries_block = "\n\n".join(
        f"[{i}/{len(intermediates)}]\n{s}" for i, s in enumerate(intermediates, 1)
    )
    prompt = _REDUCE_PROMPT.format(
        book_name=book_name, summaries=summaries_block,
        target=_FINAL_SUMMARY_TARGET_CHARS,
    )
    return _BACKEND.ask(prompt, model=model, options=_REDUCE_OPTIONS).strip()


def _parse_combined_output(text: str) -> tuple[str, dict[str, str]]:
    """Qwen の一括出力から (書籍サマリ, {キャラ名: サマリ}) を抽出する。"""
    summary = ""
    char_summaries: dict[str, str] = {}

    m = re.search(
        r"\[SUMMARY\](.*?)(?=\[CHARACTERS\]|\[CHARACTER_DETAIL:|$)",
        text, re.DOTALL,
    )
    if m:
        summary = m.group(1).strip()

    for m in re.finditer(
        r"\[CHARACTER_DETAIL:([^\]]+)\](.*?)(?=\[CHARACTER_DETAIL:|$)",
        text, re.DOTALL,
    ):
        name = m.group(1).strip()
        detail = m.group(2).strip()
        if name and detail:
            char_summaries[name] = detail

    return summary, char_summaries


def _log(cb: Callable[[str], None] | None, msg: str) -> None:
    if cb is not None:
        cb(msg)
