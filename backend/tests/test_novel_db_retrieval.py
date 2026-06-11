"""services/novel_db/retrieval.py の単体テスト。

外部依存（hybrid_search / embed_batch / LLM）はモック化してロジックのみを検証する。
"""
from __future__ import annotations

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

        with patch("services.novel_db.retrieval.load_all_pages_of_book", mock_load), \
             patch("services.novel_db.retrieval.hybrid_search", mock_hybrid):
            result = retrieve(db_conn, "質問", Scope("book", "b1"))

        mock_load.assert_called_once()
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

        with patch("services.novel_db.retrieval.load_all_pages_of_book", mock_load), \
             patch("services.novel_db.retrieval.hybrid_search", mock_hybrid), \
             patch("services.novel_db.retrieval.search_book_summaries", mock_summaries), \
             patch("services.novel_db.retrieval.load_summaries_for_books", mock_load_summaries):
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

        with patch("services.novel_db.retrieval.hybrid_search", mock_hybrid), \
             patch("services.novel_db.retrieval.search_book_summaries", mock_summaries), \
             patch("services.novel_db.retrieval.load_summaries_for_books", mock_load_summaries):
            result = retrieve(db_conn, "Q", Scope("all"))

        mock_hybrid.assert_called_once()
        assert result.hits == [hit]

    def test_scope_book_returns_no_book_summaries(self, db_conn, monkeypatch):
        """scope=book のとき book_summaries は None になる。"""
        import services.novel_db.retrieval as ret_mod
        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_FULL_BOOK_MODE", False)
        monkeypatch.setattr(ret_mod, "NOVEL_DB_QA_EXPAND_ENABLED", False)
        mock_hybrid = MagicMock(return_value=[_make_hit("b", 1)])
        mock_summaries = MagicMock(return_value=[])

        with patch("services.novel_db.retrieval.hybrid_search", mock_hybrid), \
             patch("services.novel_db.retrieval.search_book_summaries", mock_summaries):
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

        with patch("services.novel_db.retrieval.hybrid_search", mock_hybrid), \
             patch("services.novel_db.retrieval.search_book_summaries", mock_summary_hits), \
             patch("services.novel_db.retrieval.load_summaries_for_books", mock_load_summaries):
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

        with patch("services.novel_db.retrieval.expand_query", mock_expand), \
             patch("services.novel_db.retrieval.hybrid_search", mock_hybrid), \
             patch("services.novel_db.retrieval.search_book_summaries", mock_summaries), \
             patch("services.novel_db.retrieval.load_summaries_for_books", mock_load_summaries):
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

        with patch("services.novel_db.retrieval.expand_query", mock_expand), \
             patch("services.novel_db.retrieval.hybrid_search", _hybrid), \
             patch("services.novel_db.retrieval.search_book_summaries", mock_summaries), \
             patch("services.novel_db.retrieval.load_summaries_for_books", mock_load_summaries):
            result = retrieve(db_conn, "Q", Scope("all"))

        # 同一ページは 1 件にデデュープされ、スコアは 0.9 のものが採用
        assert len(result.hits) == 1
        assert result.hits[0].rrf_score == 0.9
