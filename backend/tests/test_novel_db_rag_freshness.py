"""New canonical text must not expose retained stale RAG artifacts."""

from unittest.mock import MagicMock

import pytest

from services.novel_db import book_summary_search, retrieval, search, with_db
from services.novel_db.migrations import upgrade_head
from services.novel_db.search import Scope
from services.novel_db.summary_repository import get_rag_ready_book_names, load_summaries_for_books
from tests.test_novel_db_retrieval import _make_hit
from tests.test_novel_db_search import _insert_book_with_pages


@pytest.fixture
def freshness_db(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        for name in ("ready", "pending"):
            _insert_book_with_pages(conn, name, ["検索語 新本文"])
        conn.execute("UPDATE books SET summary='old summary', ocr_done_at=datetime('now')")
        conn.execute("UPDATE books SET indexed_at=NULL WHERE name='pending'")
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
        conn.commit()
        yield conn


def test_pending_text_search_skips_embedding(freshness_db, monkeypatch):
    blocked = MagicMock(side_effect=AssertionError("must not access stale vectors"))
    monkeypatch.setattr(search, "embed_batch", blocked)
    monkeypatch.setattr(search, "get_chunks_table", blocked)
    monkeypatch.setattr(search._cfg, "NOVEL_DB_LEXICAL_BACKEND", "fts5")
    hits = search.hybrid_search(freshness_db, "検索語", Scope("book", "pending"))
    assert [hit.book_name for hit in hits] == ["pending"]
    assert "新本文" in hits[0].snippet
    blocked.assert_not_called()


def test_vector_prefilters_ready_books(freshness_db, monkeypatch):
    monkeypatch.setattr(search, "embed_batch", lambda texts: [[0.1]])
    rows = MagicMock(return_value=[])
    monkeypatch.setattr(search, "query_vector_rows", rows)
    monkeypatch.setattr(search, "get_chunks_table", lambda: object())
    search.vec_search(freshness_db, "query", Scope("all"))
    assert rows.call_args.args[2] == ["ready"]
    monkeypatch.setattr(search, "_resolve_book_names", lambda scope: ["pending", "ready"])
    search.vec_search(freshness_db, "query", Scope("series", "series"))
    assert rows.call_args.args[2] == ["ready"]


def test_pending_summaries_are_excluded(freshness_db, monkeypatch):
    blocked = MagicMock(side_effect=AssertionError("must not open stale summaries"))
    monkeypatch.setattr(book_summary_search, "get_summaries_table", blocked)
    assert book_summary_search.search_book_summaries(freshness_db, "query", Scope("book", "pending")) == []
    assert book_summary_search.find_similar_books("pending") == []
    assert load_summaries_for_books(freshness_db, ["ready", "pending"]) == {"ready": "old summary"}
    blocked.assert_not_called()


def test_summary_vectors_prefilter_ready(freshness_db, monkeypatch):
    table = MagicMock()
    table.count_rows.return_value = 2
    builder = table.search.return_value
    for method in ("limit", "select", "where"):
        getattr(builder, method).return_value = builder
    builder.to_list.return_value = [{"book_name": "ready", "_distance": 0.1}]
    monkeypatch.setattr(book_summary_search, "get_summaries_table", lambda: table)
    monkeypatch.setattr(book_summary_search, "embed_batch", lambda texts: [[0.1]])
    assert book_summary_search.search_book_summaries(freshness_db, "query", Scope("all")) == [("ready", 0.1)]
    builder.where.assert_called_once_with("book_name IN ('ready')", prefilter=True)


def test_rag_excludes_pending_lexical_hits(freshness_db, monkeypatch):
    monkeypatch.setattr(retrieval, "NOVEL_DB_QA_FULL_BOOK_MODE", False)
    monkeypatch.setattr(retrieval, "NOVEL_DB_QA_EXPAND_ENABLED", False)
    monkeypatch.setattr(retrieval, "hybrid_search", lambda *a, **k: [_make_hit("pending", 1), _make_hit("ready", 1)])
    monkeypatch.setattr(retrieval, "search_book_summaries", lambda *a, **k: [("pending", 0.0)])
    result = retrieval.retrieve(freshness_db, "query", Scope("all"))
    assert [h.book_name for h in result.hits] == ["ready"]
    assert result.book_summaries == {"ready": "old summary"}


def test_pending_rag_skips_search_and_full_book_rejects(freshness_db, monkeypatch):
    blocked = MagicMock(side_effect=AssertionError("must not retrieve pending book"))
    for name in ("hybrid_search", "expand_query", "load_all_pages_of_book"):
        monkeypatch.setattr(retrieval, name, blocked)
    monkeypatch.setattr(retrieval, "NOVEL_DB_QA_FULL_BOOK_MODE", False)
    assert retrieval.retrieve(freshness_db, "query", Scope("book", "pending")).hits == []
    monkeypatch.setattr(retrieval, "NOVEL_DB_QA_FULL_BOOK_MODE", True)
    with pytest.raises(ValueError, match="RAG is not available"):
        retrieval.retrieve(freshness_db, "query", Scope("book", "pending"))
    blocked.assert_not_called()


def test_eligibility_follows_invalidation(freshness_db):
    assert get_rag_ready_book_names(freshness_db) == ["ready"]
    freshness_db.execute("UPDATE books SET indexed_at=NULL WHERE name='ready'")
    assert get_rag_ready_book_names(freshness_db) == []
    freshness_db.execute("UPDATE books SET indexed_at=datetime('now') WHERE name='pending'")
    assert get_rag_ready_book_names(freshness_db, ["pending"]) == ["pending"]


def test_retained_real_summary_vectors_do_not_return_pending(freshness_db, monkeypatch):
    from services.novel_db.lance_store import get_summaries_table
    from tests.test_novel_db_search_summary import _vec

    table = get_summaries_table()
    for name, vector in (("ready", _vec(0)), ("pending", _vec(1))):
        book_id = freshness_db.execute("SELECT id FROM books WHERE name=?", (name,)).fetchone()[0]
        table.add([{"book_id": book_id, "book_name": name, "embedding": vector}])
    monkeypatch.setattr(book_summary_search, "embed_batch", lambda texts: [_vec(1)])
    assert [
        name
        for name, _ in book_summary_search.search_book_summaries(
            freshness_db,
            "query",
            Scope("all"),
        )
    ] == ["ready"]
    assert book_summary_search.find_similar_books("ready") == []
    assert table.count_rows() == 2


def test_real_vector_filter_escapes_book_name(freshness_db, monkeypatch):
    from services.novel_db.lance_store import get_chunks_table
    from tests.test_novel_db_search_summary import _vec

    name = "book'quoted"
    _insert_book_with_pages(freshness_db, name, ["current text"])
    table = get_chunks_table()
    table.add(
        [
            {
                "chunk_id": 900,
                "book_name": name,
                "page_no": 1,
                "text": "current text",
                "char_count": 12,
                "page_count": 1,
                "embedding": _vec(0),
            }
        ]
    )
    table.add(
        [
            {
                "chunk_id": 901,
                "book_name": "pending",
                "page_no": 1,
                "text": "old text",
                "char_count": 12,
                "page_count": 1,
                "embedding": _vec(0),
            }
        ]
    )
    monkeypatch.setattr(search, "embed_batch", lambda texts: [_vec(0)])
    rows = search.vec_search(freshness_db, "query", Scope("all"))
    assert [row[0] for row in rows] == [name]
    assert table.count_rows() == 2
