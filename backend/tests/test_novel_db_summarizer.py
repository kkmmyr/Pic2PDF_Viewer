"""services/novel_db/summarizer.py の単体テスト。

Qwen 呼び出し（`ask`）はモックする。本テストは:
- _chunk_for_map: チャンク分割ロジックの境界
- _load_body_text: フィルタ（min_chars / body_page_margin）の挙動
- summarize_book: 事実抽出 → 執筆 → 編集の呼び出し順
- update_book_summary / load_summaries_for_books: DB 入出力
を確認する。
"""

from unittest.mock import patch

import pytest

from services.novel_db import with_db
from services.novel_db._prompts import parse_combined_output
from services.novel_db.generation_quality import (
    choose_publishable_prose,
    select_pages_across_book,
)
from services.novel_db.lance_store import get_summaries_table
from services.novel_db.migrations import upgrade_head
from services.novel_db.summarizer import (
    _chunk_for_map,
    _load_body_text,
    load_summaries_for_books,
    summarize_book,
    summarize_book_with_characters,
    update_book_summary,
)

# ---------------------------------------------------------------------------
# _chunk_for_map
# ---------------------------------------------------------------------------


def test_chunk_short_text_returns_single_chunk():
    text = "short body"
    assert _chunk_for_map(text) == [text]


def test_chunk_long_text_splits_into_multiple():
    # 100,000 字（最大書籍と同等）
    text = ("a" * 1000 + "\n") * 100
    chunks = _chunk_for_map(text)
    assert len(chunks) >= 2
    assert len(chunks) <= 8  # _MAP_MAX_CHUNKS の上限
    # 結合すれば元のテキストに（ほぼ）戻る（行末改行差は除く）
    rejoined = "\n".join(chunks)
    assert rejoined.replace("\n", "") == text.replace("\n", "")


def test_chunk_respects_max_chunks_for_huge_text():
    # 200,000 字超でも最大 8 チャンク以内に収まる
    text = ("x" * 2000 + "\n") * 100
    chunks = _chunk_for_map(text)
    assert len(chunks) <= 8


# ---------------------------------------------------------------------------
# _load_body_text
# ---------------------------------------------------------------------------


@pytest.fixture
def db_with_book(tmp_data_dir):
    """1 冊（10 ページ）の最小データを入れた novel.db を返す。"""
    upgrade_head()
    with with_db() as conn:
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("test-book", "/x.pdf", "/imgs", 10),
        )
        book_id = cur.lastrowid
        for page_no in range(1, 11):
            text = "本文" * (200 if 3 <= page_no <= 8 else 50)
            conn.execute(
                "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) VALUES (?, ?, ?, ?, ?)",
                (book_id, page_no, None, text, len(text)),
            )
        conn.commit()
    return book_id


def test_load_body_text_filters_margin_and_min_chars(db_with_book):
    with with_db() as conn:
        text = _load_body_text(
            conn,
            db_with_book,
            page_count=10,
            min_chars=300,
            body_page_margin=2,
        )
    # body_page_margin=2 → page_no 3〜8 を採用
    # min_chars=300 → 「本文」(2 字) × 200 = 400 字なので採用
    # margin の 2 ページ分（page_no 1, 2, 9, 10）は除外
    assert text.count("本文") == 200 * 6  # 3..8 の 6 ページ × 200 文字


def test_load_body_text_returns_empty_when_all_filtered(db_with_book):
    with with_db() as conn:
        text = _load_body_text(
            conn,
            db_with_book,
            page_count=10,
            min_chars=10000,
            body_page_margin=0,
        )
    assert text == ""


# ---------------------------------------------------------------------------
# summarize_book / update / load
# ---------------------------------------------------------------------------


def test_summarize_book_extracts_facts_then_writes_and_edits(db_with_book):
    with patch("services.novel_db._llm_backend.QWEN_BACKEND.ask") as mock_ask:
        mock_ask.side_effect = [
            "[BOOK_FACTS]\n- [page 3] 主人公が事件を解決した。\n[CHARACTER_FACT:主人公]\n- [page 3] 事件を解決した。",
            "主人公が事件を解決した。",
            "主人公は事件の原因を調べ、問題を解決した。",
        ]
        with with_db() as conn:
            summary = summarize_book(
                conn,
                "test-book",
                min_chars=100,
                body_page_margin=2,
            )
    assert summary == "主人公は事件の原因を調べ、問題を解決した。"
    assert mock_ask.call_count == 3
    prompts = [call.args[0] for call in mock_ask.call_args_list]
    assert "[page 3]" in prompts[0]
    assert "ページ根拠付きで抽出した事実" in prompts[1]
    assert "意味を変えずに読みやすい完成文" in prompts[2]


def test_summarize_book_long_input_extracts_every_page_block(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("big-book", "/x.pdf", "/imgs", 60),
        )
        book_id = cur.lastrowid
        # 各ページ 5000 字 × 60 ページ = 300,000 字（map_max_chunks 上限近く）
        for page_no in range(1, 61):
            text = "あ" * 5000
            conn.execute(
                "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) VALUES (?, ?, ?, ?, ?)",
                (book_id, page_no, None, text, len(text)),
            )
        conn.commit()

    fact_response = "[BOOK_FACTS]\n- [page 6] 出来事が進んだ。\n[CHARACTER_FACT:主人公]\n- [page 6] 主人公が行動した。"

    def fake_ask(prompt, **_kwargs):
        if "完成したあらすじや人物紹介を書く前の材料" in prompt:
            return fact_response
        if "ページ根拠付きで抽出した事実" in prompt:
            return "長編の初稿。"
        return "長編の最終要約。"

    with patch(
        "services.novel_db._llm_backend.QWEN_BACKEND.ask",
        side_effect=fake_ask,
    ) as mock_ask:
        with with_db() as conn:
            summary = summarize_book(
                conn,
                "big-book",
                min_chars=100,
                body_page_margin=5,
            )
    assert summary == "長編の最終要約。"
    extraction_prompts = [
        call.args[0] for call in mock_ask.call_args_list if "完成したあらすじや人物紹介を書く前の材料" in call.args[0]
    ]
    assert len(extraction_prompts) >= 2
    combined_prompts = "\n".join(extraction_prompts)
    assert "[page 6]" in combined_prompts
    assert "[page 55]" in combined_prompts


def test_summarize_book_raises_for_missing_book(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        with pytest.raises(ValueError, match="book not found"):
            summarize_book(conn, "no-such-book")


def test_summarize_book_raises_for_empty_body(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            ("empty-book", "/x.pdf", "/imgs", 5),
        )
        book_id = cur.lastrowid
        for page_no in range(1, 6):
            conn.execute(
                "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) VALUES (?, ?, ?, ?, ?)",
                (book_id, page_no, None, "", 0),
            )
        conn.commit()

        with pytest.raises(ValueError, match="no body content"):
            summarize_book(conn, "empty-book")


def test_summary_and_characters_are_written_and_edited_separately(db_with_book):
    with with_db() as conn:
        conn.execute(
            "UPDATE pages SET full_text = ?, char_count = ? WHERE book_id = ? AND page_no = 3",
            ("レティは事件を調査し、友人を助けた。", 1000, db_with_book),
        )
        conn.commit()

    responses = [
        "[BOOK_FACTS]\n- [page 3] レティが事件を解決した。\n"
        "[CHARACTER_FACT:レティ]\n- [page 3] レティは主人公で、友人を助けた。",
        "レティが事件を解決した。",
        "レティは事件を調査し、友人を助けて解決へ導いた。",
        "レティは主人公である。",
        "レティは主人公として事件を調査し、友人を助けた。",
    ]
    with patch("services.novel_db._llm_backend.QWEN_BACKEND.ask") as mock_ask:
        mock_ask.side_effect = responses
        with with_db() as conn:
            summary, characters = summarize_book_with_characters(
                conn,
                "test-book",
                min_chars=100,
                body_page_margin=2,
            )

    assert summary == "レティは事件を調査し、友人を助けて解決へ導いた。"
    assert characters == {"レティ": "レティは主人公として事件を調査し、友人を助けた。"}
    prompts = [call.args[0] for call in mock_ask.call_args_list]
    assert any("事実抽出工程の人物メモ" in prompt for prompt in prompts)
    assert any("人物説明の初稿" in prompt for prompt in prompts)


def test_parse_combined_output_preserves_full_unmarked_summary():
    long_summary = "因果関係を省略しない説明。" * 300
    summary, characters = parse_combined_output(
        f"{long_summary}\n[CHARACTERS]\nレティ\n[CHARACTER_DETAIL:レティ]\n人物像",
    )

    assert len(summary) > 3000
    assert summary == long_summary
    assert characters == {"レティ": "人物像"}


def test_generation_rejects_fact_output_without_book_facts(db_with_book):
    response = """[CHARACTER_FACT:レティ]
- [page 3] 人物事実だけが返された。"""
    with patch("services.novel_db._llm_backend.QWEN_BACKEND.ask") as mock_ask:
        mock_ask.return_value = response
        with with_db() as conn:
            with pytest.raises(ValueError, match=r"did not contain \[BOOK_FACTS\]"):
                summarize_book_with_characters(
                    conn,
                    "test-book",
                    min_chars=100,
                    body_page_margin=2,
                )


def test_character_evidence_selection_keeps_first_and_final_occurrence():
    pages = [(page_no, str(page_no) * 1000) for page_no in range(1, 21)]
    selected = select_pages_across_book(pages, max_chars=6500, coverage_bins=5)

    selected_page_nos = [page_no for page_no, _ in selected]
    assert selected_page_nos[0] == 1
    assert selected_page_nos[-1] == 20
    assert any(5 <= page_no <= 16 for page_no in selected_page_nos)


def test_character_evidence_selection_fails_instead_of_dropping_final_page():
    pages = [(1, "a" * 6000), (2, "b" * 100), (3, "c" * 3000)]

    with pytest.raises(ValueError, match="first and final"):
        select_pages_across_book(pages, max_chars=8000)


def test_editor_failure_falls_back_to_valid_draft():
    draft = "レティは主人公として事件を調査した。"
    edited = "[SUMMARY]\nレティは主人公である。"

    assert choose_publishable_prose(draft, edited, required_subject="レティ") == draft


def test_update_and_load_summary_roundtrip(db_with_book):
    with with_db() as conn:
        update_book_summary(conn, "test-book", "これはテスト要約")
        loaded = load_summaries_for_books(conn, ["test-book"])

    assert loaded == {"test-book": "これはテスト要約"}


def test_load_summaries_skips_null_and_empty(tmp_data_dir):
    """summary が NULL / 空文字の書籍は load 結果に含まれない。"""
    upgrade_head()
    with with_db() as conn:
        for name, summary in [("a", "ok"), ("b", None), ("c", "")]:
            cur = conn.execute(
                "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                (name, f"/{name}.pdf", "/imgs", 10),
            )
            if summary is not None:
                conn.execute(
                    "UPDATE books SET summary = ? WHERE id = ?",
                    (summary, cur.lastrowid),
                )
        conn.commit()

        loaded = load_summaries_for_books(conn, ["a", "b", "c"])

    assert loaded == {"a": "ok"}


def test_load_summaries_for_empty_input_returns_empty():
    # DB 接続不要（早期 return する）
    assert load_summaries_for_books(None, []) == {}  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# B-8: 書籍サマリ embedding と検索インデックス
# ---------------------------------------------------------------------------


def test_update_book_summary_indexes_vector(db_with_book):
    """update_book_summary が summary を保存し、LanceDB summaries にも upsert する。"""
    with patch("services.novel_db.summarizer.embed_batch") as mock_embed:
        # bge-m3 は 1024 次元
        mock_embed.return_value = [[0.1] * 1024]
        with with_db() as conn:
            update_book_summary(conn, "test-book", "テストサマリ")
            # books.summary 更新
            row = conn.execute(
                "SELECT summary FROM books WHERE name = ?",
                ("test-book",),
            ).fetchone()
            assert row[0] == "テストサマリ"
        # LanceDB summaries に 1 件
        table = get_summaries_table()
        n = table.count_rows()
        assert n == 1
    mock_embed.assert_called_once_with(["テストサマリ"])


def test_update_book_summary_handles_embed_failure(db_with_book):
    """embedder 失敗時はサマリ本文だけ保存し、vec 側は空のまま続行する。"""
    with patch("services.novel_db.summarizer.embed_batch") as mock_embed:
        mock_embed.side_effect = TimeoutError("ollama timeout")
        with with_db() as conn:
            update_book_summary(conn, "test-book", "テスト")
            # 本文は保存されている
            row = conn.execute(
                "SELECT summary FROM books WHERE name = ?",
                ("test-book",),
            ).fetchone()
            assert row[0] == "テスト"
        # LanceDB summaries は空のまま
        table = get_summaries_table()
        assert table.count_rows() == 0


def test_update_book_summary_replaces_existing_vector(db_with_book):
    """同 book_id への 2 回目の update は vec を置き換える（重複 INSERT しない）。"""
    with patch("services.novel_db.summarizer.embed_batch") as mock_embed:
        mock_embed.return_value = [[0.1] * 1024]
        with with_db() as conn:
            update_book_summary(conn, "test-book", "v1")
            update_book_summary(conn, "test-book", "v2")
        # LanceDB summaries に 1 件のみ（重複なし）
        table = get_summaries_table()
        assert table.count_rows() == 1


def test_update_book_summary_raises_for_missing_book(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        with pytest.raises(ValueError, match="book not found"):
            update_book_summary(conn, "no-such-book", "サマリ")
