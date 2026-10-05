"""services/novel_db/retrieval.py の単体テスト。

外部依存（hybrid_search / embed_batch / LLM）はモック化してロジックのみを検証する。
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from services.novel_db.retrieval import retrieve
from services.novel_db.search import Scope, SearchHit


def _make_hit(book_name: str, page_no: int, score: float = 1.0) -> SearchHit:
    return SearchHit(
        book_name=book_name,
        page_no=page_no,
        snippet="snippet",
        has_highlight=False,
        image_url=None,
        rrf_score=score,
    )


@pytest.fixture
def db_conn(tmp_data_dir):
    from services.novel_db import with_db
    from services.novel_db.migrations import upgrade_head

    upgrade_head()
    with with_db() as conn:
        for name in ("b", "b1", "book-a"):
            book_id = conn.execute(
                "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
                "VALUES (?, '', '', 5, datetime('now'))",
                (name,),
            ).lastrowid
            for page_no in range(1, 6):
                body = f"{name} canonical page {page_no}"
                conn.execute(
                    "INSERT INTO pages(book_id,page_no,full_text,char_count,page_type,index_eligible) "
                    "VALUES(?,?,?,?,'narrative',1)",
                    (book_id, page_no, body, len(body)),
                )
        conn.commit()
        yield conn


class TestRetrieveFullBookMode:
    """full_book_mode（scope=book + 設定有効）のブランチを検証する。"""

    def test_full_book_mode_calls_load_all_pages(self, db_conn, monkeypatch):
        """full_book_mode のとき load_all_pages_of_book が呼ばれる。"""
        import services.novel_db.retrieval as ret_mod

        expected_hits = [_make_hit("b1", 1), _make_hit("b1", 2)]
        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_FULL_BOOK_MODE", True)
        mock_load = MagicMock(return_value=expected_hits)
        mock_hybrid = MagicMock(return_value=[])

        with (
            patch("services.novel_db.retrieval.load_all_pages_of_book", mock_load),
            patch("services.novel_db.retrieval.hybrid_search", mock_hybrid),
        ):
            result = retrieve(db_conn, "質問", Scope("book", "b1"))

        mock_load.assert_called_once()
        assert mock_load.call_args.kwargs["min_chars"] == 0
        assert mock_load.call_args.kwargs["body_page_margin"] == 0
        mock_hybrid.assert_not_called()
        assert result.hits == expected_hits
        assert result.book_summaries is None

    def test_full_book_mode_inactive_for_all_scope(self, db_conn, monkeypatch):
        """full_book_mode=True でも scope=all なら通常 RAG が走る。"""
        import services.novel_db.retrieval as ret_mod

        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_FULL_BOOK_MODE", True)
        mock_load = MagicMock(return_value=[])
        mock_hybrid = MagicMock(return_value=[])
        mock_summaries = MagicMock(return_value=[])
        mock_load_summaries = MagicMock(return_value={})

        with (
            patch("services.novel_db.retrieval.load_all_pages_of_book", mock_load),
            patch("services.novel_db.retrieval.hybrid_search", mock_hybrid),
            patch("services.novel_db.retrieval.search_book_summaries", mock_summaries),
            patch("services.novel_db.retrieval.load_summaries_for_books", mock_load_summaries),
        ):
            retrieve(db_conn, "Q", Scope("all"))

        mock_load.assert_not_called()
        mock_hybrid.assert_called()


class TestRetrieveNormalRAG:
    """通常 RAG モード（full_book_mode=False）のブランチを検証する。"""

    def test_normal_rag_calls_hybrid_search(self, db_conn, monkeypatch):
        import services.novel_db.retrieval as ret_mod

        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_FULL_BOOK_MODE", False)
        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_EXPAND_ENABLED", False)
        hit = _make_hit("book-a", 5, score=0.5)
        mock_hybrid = MagicMock(return_value=[hit])
        mock_summaries = MagicMock(return_value=[])
        mock_load_summaries = MagicMock(return_value={})

        with (
            patch("services.novel_db.retrieval.hybrid_search", mock_hybrid),
            patch("services.novel_db.retrieval.search_book_summaries", mock_summaries),
            patch("services.novel_db.retrieval.load_summaries_for_books", mock_load_summaries),
        ):
            result = retrieve(db_conn, "Q", Scope("all"))

        mock_hybrid.assert_called_once()
        assert mock_hybrid.call_args.kwargs["min_chars"] == 0
        assert mock_hybrid.call_args.kwargs["body_page_margin"] == 0
        assert result.hits == [replace(hit, snippet="book-a canonical page 5")]

    def test_scope_book_returns_no_book_summaries(self, db_conn, monkeypatch):
        """scope=book のとき book_summaries は None になる。"""
        import services.novel_db.retrieval as ret_mod

        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_FULL_BOOK_MODE", False)
        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_EXPAND_ENABLED", False)
        mock_hybrid = MagicMock(return_value=[_make_hit("b", 1)])
        mock_summaries = MagicMock(return_value=[])

        with (
            patch("services.novel_db.retrieval.hybrid_search", mock_hybrid),
            patch("services.novel_db.retrieval.search_book_summaries", mock_summaries),
        ):
            result = retrieve(db_conn, "Q", Scope("book", "b"))

        mock_summaries.assert_not_called()
        assert result.book_summaries is None

    def test_scope_all_returns_book_summaries(self, db_conn, monkeypatch):
        """scope=all のとき book_summaries dict が返る。"""
        import services.novel_db.retrieval as ret_mod

        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_FULL_BOOK_MODE", False)
        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_EXPAND_ENABLED", False)
        mock_hybrid = MagicMock(return_value=[_make_hit("b", 1)])
        mock_summary_hits = MagicMock(return_value=[("b", 0.1)])
        mock_load_summaries = MagicMock(return_value={"b": "サマリ本文"})

        with (
            patch("services.novel_db.retrieval.hybrid_search", mock_hybrid),
            patch("services.novel_db.retrieval.search_book_summaries", mock_summary_hits),
            patch("services.novel_db.retrieval.load_summaries_for_books", mock_load_summaries),
        ):
            result = retrieve(db_conn, "Q", Scope("all"))

        assert result.book_summaries == {"b": "サマリ本文"}

    def test_query_expansion_calls_hybrid_per_query(self, db_conn, monkeypatch):
        """NOVEL_DB_QA_EXPAND_ENABLED=True のとき expand_query 結果の件数だけ hybrid_search が呼ばれる。"""
        import services.novel_db.retrieval as ret_mod

        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_FULL_BOOK_MODE", False)
        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_EXPAND_ENABLED", True)
        mock_expand = MagicMock(return_value=["Q1", "Q2"])
        mock_hybrid = MagicMock(return_value=[])
        mock_summaries = MagicMock(return_value=[])
        mock_load_summaries = MagicMock(return_value={})

        with (
            patch("services.novel_db.retrieval.expand_query", mock_expand),
            patch("services.novel_db.retrieval.hybrid_search", mock_hybrid),
            patch("services.novel_db.retrieval.search_book_summaries", mock_summaries),
            patch("services.novel_db.retrieval.load_summaries_for_books", mock_load_summaries),
        ):
            retrieve(db_conn, "元Q", Scope("all"))

        assert mock_hybrid.call_count == 2

    def test_result_deduplicates_by_key_keeps_higher_score(self, db_conn, monkeypatch):
        """同一 (book_name, page_no) は最高スコアのものだけ残る。"""
        import services.novel_db.retrieval as ret_mod

        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_FULL_BOOK_MODE", False)
        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_EXPAND_ENABLED", True)
        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_TOP_K", 10)
        hit_low = _make_hit("b", 1, score=0.1)
        hit_high = _make_hit("b", 1, score=0.9)
        mock_expand = MagicMock(return_value=["Q1", "Q2"])
        call_count = {"n": 0}

        def _hybrid(*args, **kwargs):
            call_count["n"] += 1
            return [hit_low] if call_count["n"] == 1 else [hit_high]

        mock_summaries = MagicMock(return_value=[])
        mock_load_summaries = MagicMock(return_value={})

        with (
            patch("services.novel_db.retrieval.expand_query", mock_expand),
            patch("services.novel_db.retrieval.hybrid_search", _hybrid),
            patch("services.novel_db.retrieval.search_book_summaries", mock_summaries),
            patch("services.novel_db.retrieval.load_summaries_for_books", mock_load_summaries),
        ):
            result = retrieve(db_conn, "Q", Scope("all"))

        # 同一ページは 1 件にデデュープされ、スコアは 0.9 のものが採用
        assert len(result.hits) == 1
        assert result.hits[0].rrf_score == 0.9


@pytest.fixture
def normal_rag(monkeypatch):
    import services.novel_db.retrieval as module

    monkeypatch.setattr(module, "NOVEL_DB_QA_FULL_BOOK_MODE", False)
    monkeypatch.setattr(module, "NOVEL_DB_QA_EXPAND_ENABLED", False)
    monkeypatch.setattr(module, "search_book_summaries", lambda *args, **kwargs: [])
    monkeypatch.setattr(module, "load_summaries_for_books", lambda *args, **kwargs: {})
    return module


def test_normal_rag_prompt_keeps_answer_beyond_display_snippet(db_conn, normal_rag, monkeypatch):
    from services.novel_db.prompt_builder import build_prompt

    body = "冒頭の文章。" * 50 + "答えは三日月の石です。"
    db_conn.execute("UPDATE pages SET full_text=?,char_count=? WHERE page_no=1", (body, len(body)))
    db_conn.commit()
    hit = replace(_make_hit("b", 1), snippet=body[:200], has_highlight=True)
    monkeypatch.setattr(normal_rag, "hybrid_search", lambda *args, **kwargs: [hit])
    result = retrieve(db_conn, "答えは何？", Scope("book", "b"))
    assert result.hits[0].snippet == body
    assert "答えは三日月の石です。" in build_prompt("答えは何？", result.hits, Scope("book", "b"))
    assert result.hits[0].has_highlight is False
    assert hit.snippet == body[:200] and hit.has_highlight  # Search UI object is unchanged.


def test_canonical_html_like_body_is_preserved(db_conn, normal_rag, monkeypatch):
    from services.novel_db.prompt_builder import build_chat_context_block, build_prompt

    body = "式は <name> と <mark>原文</mark> と a < b です。"
    db_conn.execute("UPDATE pages SET full_text=?,char_count=? WHERE page_no=1", (body, len(body)))
    db_conn.commit()
    monkeypatch.setattr(normal_rag, "hybrid_search", lambda *args, **kwargs: [_make_hit("b", 1)])
    result = retrieve(db_conn, "式", Scope("book", "b"))
    assert result.hits[0].snippet == body
    assert not result.hits[0].has_highlight
    assert body in build_prompt("式", result.hits, Scope("book", "b"))
    assert body in build_chat_context_block(result.hits, Scope("book", "b"))


@pytest.mark.parametrize("failure", ["missing", "ineligible", "empty", "zero"])
def test_missing_or_ineligible_canonical_page_fails_closed(db_conn, normal_rag, monkeypatch, failure):
    page_no = 0 if failure == "zero" else 1
    if failure == "missing":
        db_conn.execute("DELETE FROM pages WHERE page_no=1")
    elif failure == "ineligible":
        db_conn.execute("UPDATE pages SET index_eligible=0 WHERE page_no=1")
    elif failure == "empty":
        db_conn.execute("UPDATE pages SET full_text=' ' WHERE page_no=1")
    db_conn.commit()
    monkeypatch.setattr(normal_rag, "hybrid_search", lambda *args, **kwargs: [_make_hit("b", page_no)])
    with pytest.raises(ValueError, match="invalid page|canonical body unavailable"):
        retrieve(db_conn, "質問", Scope("book", "b"))


def test_same_page_number_reads_correct_book(db_conn, normal_rag, monkeypatch):
    hits = [_make_hit("b", 1, 0.8), _make_hit("b1", 1, 0.6)]
    monkeypatch.setattr(normal_rag, "hybrid_search", lambda *args, **kwargs: hits)
    result = retrieve(db_conn, "質問", Scope("all"))
    assert [h.snippet for h in result.hits] == ["b canonical page 1", "b1 canonical page 1"]
    assert [h.rrf_score for h in result.hits] == [0.8, 0.6]


@pytest.mark.parametrize("full_book_mode", [False, True])
@pytest.mark.parametrize("book_name", ["b", "missing-book"])
def test_unready_book_is_rejected_in_both_modes(db_conn, monkeypatch, full_book_mode, book_name):
    import services.novel_db.retrieval as ret_mod

    db_conn.execute("UPDATE books SET indexed_at=NULL WHERE name='b'")
    db_conn.commit()
    monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_FULL_BOOK_MODE", full_book_mode)
    load = MagicMock()
    search = MagicMock()
    monkeypatch.setattr(ret_mod, "load_all_pages_of_book", load)
    monkeypatch.setattr(ret_mod, "hybrid_search", search)
    with pytest.raises(ret_mod.RagNotReady, match="RAG is not available"):
        retrieve(db_conn, "質問", Scope("book", book_name))
    load.assert_not_called()
    search.assert_not_called()


@pytest.mark.parametrize("full_book_mode", [False, True])
@pytest.mark.parametrize("scope", [Scope("all"), Scope("series", "empty-series")])
def test_empty_ready_all_or_series_preserves_empty_result(db_conn, monkeypatch, full_book_mode, scope):
    import services.novel_db.retrieval as ret_mod

    db_conn.execute("UPDATE books SET indexed_at=NULL")
    db_conn.commit()
    monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_FULL_BOOK_MODE", full_book_mode)
    if scope.type == "series":
        monkeypatch.setattr(ret_mod, "resolve_book_names", lambda _: ["b", "b1"])
    load = MagicMock()
    search = MagicMock()
    monkeypatch.setattr(ret_mod, "load_all_pages_of_book", load)
    monkeypatch.setattr(ret_mod, "hybrid_search", search)
    result = retrieve(db_conn, "質問", scope)
    assert result.hits == []
    assert result.book_summaries is None
    assert result.qa_options == ret_mod.LLM_OPTIONS
    load.assert_not_called()
    search.assert_not_called()
