"""page-level LanceDB ICU indexの構築・世代・検索契約。"""

from __future__ import annotations

import sqlite3

import pytest

from services.novel_db import page_fts
from services.novel_db.connection import with_db
from services.novel_db.lance_store import get_db
from services.novel_db.migrations import upgrade_head
from services.novel_db.page_fts import (
    PageFtsBuildConflict,
    PageFtsUnavailable,
    build_page_fts_index,
    build_page_fts_snippet,
    get_page_fts_state,
    mark_page_fts_stale,
    search_page_fts,
)
from services.novel_db.search import Scope, sanitize_snippet


def _insert_book(conn: sqlite3.Connection, name: str, pages: list[tuple[str, bool]]) -> int:
    cursor = conn.execute(
        "INSERT INTO books (name, pdf_path, images_dir, page_count) VALUES (?, '', '', ?)",
        (name, len(pages)),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("failed to create test book")
    book_id = cursor.lastrowid
    for page_no, (text, eligible) in enumerate(pages, start=1):
        conn.execute(
            "INSERT INTO pages "
            "(book_id, page_no, full_text, char_count, page_type, index_eligible) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (book_id, page_no, text, len(text), "narrative" if eligible else "toc", eligible),
        )
    return book_id


@pytest.fixture
def populated_page_fts_db(tmp_data_dir) -> None:
    upgrade_head()
    with with_db() as conn:
        _insert_book(
            conn,
            "book-a",
            [
                ("王女は薔薇園で秘密の騎士と出会った。", True),
                ("二頁目では遠征の準備が始まった。", True),
                ("薔薇園という語を含む目次。", False),
            ],
        )
        _insert_book(conn, "book-b", [("別の物語では薔薇園が祝宴の会場になった。", True)])
        conn.commit()


def test_build_activates_complete_icu_index_and_searches_by_scope(populated_page_fts_db) -> None:
    with with_db() as conn:
        result = build_page_fts_index(conn)
        state = get_page_fts_state(conn)
        assert state is not None
        assert state.status == "active"
        assert state.source_revision == state.active_source_revision == 0
        assert state.active_table_name == result.table_name
        assert state.row_count == result.row_count == 3
        assert state.source_sha256 == result.source_sha256

        all_rows = search_page_fts(conn, "薔薇園", Scope(type="all"), top=10)
        assert {(row[0], row[1]) for row in all_rows} == {("book-a", 1), ("book-b", 1)}
        assert all("<mark>" in row[2] for row in all_rows)

        scoped = search_page_fts(conn, "薔薇園", Scope(type="book", id="book-b"), top=10)
        assert [(row[0], row[1]) for row in scoped] == [("book-b", 1)]
        assert search_page_fts(conn, "薔薇園", Scope(type="book", id="missing"), top=10) == []


def test_page_filters_are_applied_before_icu_ranking(populated_page_fts_db) -> None:
    with with_db() as conn:
        build_page_fts_index(conn)
        assert search_page_fts(conn, "遠征", Scope(type="all"), min_chars=100) == []
        assert search_page_fts(conn, "薔薇園", Scope(type="book", id="book-a"), body_page_margin=1) == []


def test_mark_stale_disables_old_active_index(populated_page_fts_db) -> None:
    with with_db() as conn:
        build_page_fts_index(conn)
        mark_page_fts_stale(conn)
        conn.commit()
        state = get_page_fts_state(conn)
        assert state is not None
        assert state.status == "stale"
        assert state.source_revision == 1
        assert state.active_source_revision == 0
        with pytest.raises(PageFtsUnavailable, match="missing or stale"):
            search_page_fts(conn, "薔薇園", Scope(type="all"))


def test_concurrent_source_change_rejects_activation_and_removes_scratch_table(
    populated_page_fts_db,
    monkeypatch,
) -> None:
    with with_db() as conn:
        first = build_page_fts_index(conn)
        tables_before = set(get_db().list_tables().tables)
        original_activate = page_fts._activate_index

        def activate_after_source_change(connection, **kwargs):
            mark_page_fts_stale(connection)
            connection.commit()
            return original_activate(connection, **kwargs)

        monkeypatch.setattr(page_fts, "_activate_index", activate_after_source_change)
        with pytest.raises(PageFtsBuildConflict, match="changed"):
            build_page_fts_index(conn)

        state = get_page_fts_state(conn)
        assert state is not None
        assert state.active_table_name == first.table_name
        assert state.status == "stale"
        assert set(get_db().list_tables().tables) == tables_before


def test_empty_corpus_can_be_activated_and_returns_no_hits(tmp_data_dir) -> None:
    upgrade_head()
    with with_db() as conn:
        result = build_page_fts_index(conn)
        assert result.row_count == 0
        assert search_page_fts(conn, "存在しない", Scope(type="all")) == []


def test_icu_snippet_is_safely_sanitized() -> None:
    raw = build_page_fts_snippet('<script>alert("x")</script>秘密の文章', "秘密")
    safe = sanitize_snippet(raw)
    assert "<script>" not in safe
    assert "&lt;script&gt;" in safe
    assert "<mark>秘密</mark>" in safe
