"""検索結果の順位・出典・整形と外部検索の呼出し契約。"""

from dataclasses import asdict
from unittest.mock import MagicMock

import pytest

from services.novel_db import search, with_db
from services.novel_db.migrations import upgrade_head
from services.novel_db.search import Scope
from tests.test_novel_db_search import _insert_book_with_pages


@pytest.fixture
def contract_db(tmp_data_dir):
    upgrade_head()
    with with_db() as conn:
        yield conn


def test_hybrid_ranking_duplicates_ties_and_snippet_priority(contract_db, monkeypatch):
    book = "本 /?#%&'"
    book_id = _insert_book_with_pages(contract_db, book, ["本文", "次の本文"])
    contract_db.execute(
        "UPDATE pages SET main_characters = ' アリス, , ボブ,アリス ' WHERE book_id = ? AND page_no = 1",
        (book_id,),
    )
    contract_db.commit()
    lexical = [
        (book, 1, '<mark>人</mark><img src="x">', 999),
        ("B", 1, "", -10),
        (book, 1, "ignored", 1),
        (book, 2, "FTS only", 100),
    ]
    vector = [
        ("B", 1, "<mark>" + "x" * 220, 100),
        (book, 1, "ignored vector", 0),
        ("C", 1, "<&", -10),
        ("C", 1, "later chunk", -20),
        ("D", 1, "last", -100),
    ]
    calls = []

    def lexical_call(conn, query, scope, top, **kwargs):
        calls.append(("lexical", query, scope, top, kwargs))
        return lexical

    def vector_call(conn, query, scope, top, **kwargs):
        calls.append(("vector", query, scope, top, kwargs))
        return vector

    monkeypatch.setattr(search, "lexical_search", lexical_call)
    monkeypatch.setattr(search, "vec_search", vector_call)
    scope = Scope(type="all")
    hits = search.hybrid_search(
        contract_db, "質問", scope, top=10, fts_n=4, vec_n=5, k_rrf=0, min_chars=3, body_page_margin=2
    )

    assert calls == [
        (kind, "質問", scope, top, {"min_chars": 3, "body_page_margin": 2})
        for kind, top in [("lexical", 4), ("vector", 5)]
    ]
    assert [(h.book_name, h.page_no) for h in hits] == [(book, 1), ("B", 1), ("C", 1), (book, 2), ("D", 1)]
    assert [h.rrf_score for h in hits] == pytest.approx([1 + 1 / 3 + 1 / 2, 1 / 2 + 1, 1 / 3 + 1 / 4, 1 / 4, 1 / 5])
    assert asdict(hits[0]) == {
        "book_name": book,
        "page_no": 1,
        "snippet": "<mark>人</mark>&lt;img src=&quot;x&quot;&gt;",
        "has_highlight": True,
        "image_url": "/kindle_novel/images/%E6%9C%AC%20%2F%3F%23%25%26%27/001.png",
        "rrf_score": hits[0].rrf_score,
        "main_characters": ["アリス", "ボブ", "アリス"],
    }
    assert hits[1].snippet == "&lt;mark&gt;" + "x" * 194
    assert not hits[1].has_highlight
    assert hits[2].snippet == "&lt;&amp;"
    assert hits[2].main_characters == []
    assert lexical[0][2] == '<mark>人</mark><img src="x">'


@pytest.mark.parametrize(
    "cap,top,expected", [(None, 2, ["A1", "B1"]), (1, 3, ["A1", "B1"]), (0, 3, ["A1", "B1", "A2"]), (None, 0, [])]
)
def test_equal_rrf_scores_keep_first_seen_order_and_book_limit(contract_db, monkeypatch, cap, top, expected):
    monkeypatch.setattr(search, "lexical_search", lambda *a, **k: [("A", 1, "A1", 0), ("B", 1, "B1", 0)])
    monkeypatch.setattr(search, "vec_search", lambda *a, **k: [("B", 1, "vB", 0), ("A", 1, "vA", 0), ("A", 2, "A2", 0)])
    hits = search.hybrid_search(contract_db, "query", Scope(type="all"), top=top, max_per_book=cap)
    assert [h.snippet for h in hits] == expected


def test_vector_filters_overfetch_distance_ties_and_margin(contract_db, monkeypatch):
    table = MagicMock()
    builder = table.search.return_value
    builder.limit.return_value = builder
    builder.select.return_value = builder
    builder.where.return_value = builder
    builder.to_list.return_value = [
        {"book_name": "A", "page_no": 1, "page_count": 8, "text": "cover", "_distance": 0},
        {"book_name": "A", "page_no": 4, "page_count": 8, "text": "first tie", "_distance": 0.5},
        {"book_name": "A", "page_no": 3, "page_count": 8, "text": "second tie", "_distance": 0.5},
        {"book_name": "A", "page_no": 8, "page_count": 8, "text": "back", "_distance": 0},
    ]
    monkeypatch.setattr(search, "get_chunks_table", lambda: table)
    embed = MagicMock(return_value=[[0.25]])
    monkeypatch.setattr(search, "embed_batch", embed)
    rows = search.vec_search(contract_db, "質問", Scope(type="book", id="A"), top=2, min_chars=10, body_page_margin=1)
    assert rows == [("A", 4, "first tie", 0.5), ("A", 3, "second tie", 0.5)]
    embed.assert_called_once_with(["質問"])
    table.search.assert_called_once_with([0.25])
    builder.limit.assert_called_once_with(50)
    builder.where.assert_called_once_with("char_count >= 10 AND book_name IN ('A')", prefilter=True)


@pytest.mark.parametrize("scope", [Scope(type="book"), Scope(type="series")])
def test_empty_scope_does_not_embed_or_open_vector_table(contract_db, monkeypatch, scope):
    embed, table = MagicMock(), MagicMock()
    monkeypatch.setattr(search, "embed_batch", embed)
    monkeypatch.setattr(search, "get_chunks_table", table)
    assert search.vec_search(contract_db, "質問", scope) == []
    assert search.fts_search(contract_db, "質問", scope) == []
    embed.assert_not_called()
    table.assert_not_called()


def test_fts_applies_scope_eligibility_length_and_margin(contract_db):
    for name in ["A", "B"]:
        _insert_book_with_pages(contract_db, name, ["検索本文です"] * 5)
    contract_db.execute("UPDATE pages SET index_eligible = 0 WHERE page_no = 2")
    contract_db.execute("UPDATE pages SET char_count = 1 WHERE page_no = 3")
    contract_db.commit()
    rows = search.fts_search(contract_db, "検索本文", Scope(type="book", id="A"), min_chars=3, body_page_margin=1)
    assert [(r[0], r[1]) for r in rows] == [("A", 4)]


def test_full_book_keeps_raw_text_and_applies_margin_after_filtering(contract_db):
    book_id = _insert_book_with_pages(contract_db, "A", ["<script>&生本文", "除外", "中央本文", "短", "最後の本文"])
    contract_db.execute("UPDATE pages SET index_eligible = 0 WHERE book_id = ? AND page_no = 2", (book_id,))
    contract_db.commit()
    hits = search.load_all_pages_of_book(contract_db, "A", min_chars=3)
    assert [h.page_no for h in hits] == [1, 3, 5]
    assert hits[0].snippet == "<script>&生本文"
    assert hits[0].has_highlight is False
    assert search.load_all_pages_of_book(contract_db, "A", min_chars=3, body_page_margin=1)[0].page_no == 3


@pytest.mark.parametrize("stage", ["lexical", "vector"])
def test_hybrid_does_not_hide_backend_errors(contract_db, monkeypatch, stage):
    def fail(*args, **kwargs):
        raise RuntimeError("backend unavailable")

    vector = MagicMock(return_value=[])
    monkeypatch.setattr(search, "lexical_search", fail if stage == "lexical" else lambda *a, **k: [])
    monkeypatch.setattr(search, "vec_search", fail if stage == "vector" else vector)
    with pytest.raises(RuntimeError, match="backend unavailable"):
        search.hybrid_search(contract_db, "query", Scope(type="all"))
    vector.assert_not_called()


def test_shadow_failure_preserves_fts_result_without_logging_query(contract_db, monkeypatch):
    rows = [("A", 1, "matched", -1)]
    monkeypatch.setattr(search._cfg, "NOVEL_DB_LEXICAL_BACKEND", "shadow")
    monkeypatch.setattr(search, "fts_search", lambda *a, **k: rows)

    def fail(*args, **kwargs):
        raise RuntimeError("秘密の質問を含む例外")

    monkeypatch.setattr(search, "search_page_fts", fail)
    warning = MagicMock()
    monkeypatch.setattr(search.logger, "warning", warning)
    assert search.lexical_search(contract_db, "秘密の質問", Scope(type="all")) is rows
    warning.assert_called_once()
    text = warning.call_args.args[0] % warning.call_args.args[1:]
    assert "秘密の質問" not in text
    assert "query_hash=" in text and "error_type=RuntimeError" in text


def test_fts_missing_index_returns_empty(contract_db):
    contract_db.execute("DROP TABLE pages_fts")
    assert search.fts_search(contract_db, "検索本文", Scope(type="all")) == []
