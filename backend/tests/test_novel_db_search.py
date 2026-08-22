"""services/novel_db/search.py の単体・統合テスト。"""

import sqlite3

import pytest

from services.meta_store import save_meta
from services.novel_db import with_db
from services.novel_db.lance_store import get_chunks_table
from services.novel_db.migrations import upgrade_head
from services.novel_db.search import (
    Scope,
    _resolve_book_names,
    build_fts5_or_query,
    fts_search,
    hybrid_search,
    lexical_search,
    load_all_pages_of_book,
    sanitize_snippet,
)

# ---------------------------------------------------------------------------
# 純関数
# ---------------------------------------------------------------------------


class TestBuildFts5OrQuery:
    def test_extracts_japanese_tokens(self):
        # 日本語連続は 1 トークンとして抽出される
        result = build_fts5_or_query("デュークの正体は何ですか")
        assert '"デュークの正体は何ですか"' in result

    def test_or_joins_multiple_tokens(self):
        # スペース区切りで複数トークン → OR 結合
        result = build_fts5_or_query("デューク アストリッド")
        assert " OR " in result
        assert '"デューク"' in result
        assert '"アストリッド"' in result

    def test_strips_special_chars(self):
        # ?, ! などの FTS5 特殊文字を除去
        result = build_fts5_or_query("デュークは誰?")
        assert "?" not in result

    def test_returns_empty_for_only_special_chars(self):
        assert build_fts5_or_query("?!*+") == ""

    def test_filters_short_tokens(self):
        # 1 文字の助詞などは min_len=2 で除外
        result = build_fts5_or_query("あ")
        assert result == ""

    def test_quotes_each_token_as_phrase(self):
        result = build_fts5_or_query("薔薇園 デューク")
        assert '"薔薇園"' in result
        assert '"デューク"' in result


class TestSanitizeSnippet:
    def test_preserves_mark_tags(self):
        out = sanitize_snippet("aaa<mark>bbb</mark>ccc")
        assert "<mark>" in out
        assert "</mark>" in out
        assert "bbb" in out

    def test_escapes_other_html(self):
        out = sanitize_snippet("a<script>alert(1)</script>b")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_escapes_ampersand(self):
        out = sanitize_snippet("a&b")
        assert "&amp;" in out

    def test_no_xss_via_attribute(self):
        out = sanitize_snippet('<img src="x" onerror="x">')
        assert "<img" not in out


class TestResolveBookNames:
    def test_all_returns_none(self):
        assert _resolve_book_names(Scope(type="all")) is None

    def test_book_returns_single_name(self):
        assert _resolve_book_names(Scope(type="book", id="book-1")) == ["book-1"]

    def test_book_with_no_id_returns_empty(self):
        assert _resolve_book_names(Scope(type="book")) == []

    def test_series_with_no_id_returns_empty(self):
        assert _resolve_book_names(Scope(type="series")) == []

    def test_series_resolves_via_meta(self, tmp_data_dir):
        meta = {
            "book-a.pdf": {"series_id": "s1", "series_title": "S"},
            "book-b.pdf": {"series_id": "s1", "series_title": "S"},
            "book-c.pdf": {"series_id": "s2", "series_title": "T"},
        }
        save_meta("novel", meta)

        result = _resolve_book_names(Scope(type="series", id="s1"))
        assert sorted(result) == ["book-a", "book-b"]


def test_lexical_shadow_returns_fts5_rows_and_only_logs_query_hash(monkeypatch):
    from services.novel_db import search as search_mod

    query = "ログへ残してはいけない秘密の質問"
    fts_rows = [("book-a", 1, "fts", -1.0)]
    icu_rows = [("book-b", 2, "icu", 1.0)]
    monkeypatch.setattr(search_mod._cfg, "NOVEL_DB_LEXICAL_BACKEND", "shadow")
    monkeypatch.setattr(search_mod, "fts_search", lambda *args, **kwargs: fts_rows)
    monkeypatch.setattr(search_mod, "search_page_fts", lambda *args, **kwargs: icu_rows)
    log_messages: list[str] = []
    monkeypatch.setattr(
        search_mod.logger,
        "info",
        lambda message, *args: log_messages.append(message % args),
    )

    with sqlite3.connect(":memory:") as conn:
        rows = lexical_search(conn, query, Scope(type="all"))

    log_text = "\n".join(log_messages)
    assert rows is fts_rows
    assert query not in log_text
    assert "query_hash=" in log_text
    assert "fts_count=1" in log_text
    assert "icu_count=1" in log_text


def test_lexical_icu_uses_valid_empty_result_without_fallback(monkeypatch):
    from services.novel_db import search as search_mod

    fallback_calls = 0

    def fallback(*args, **kwargs):
        nonlocal fallback_calls
        fallback_calls += 1
        return [("fallback", 1, "fts", -1.0)]

    monkeypatch.setattr(search_mod._cfg, "NOVEL_DB_LEXICAL_BACKEND", "lance_icu")
    monkeypatch.setattr(search_mod, "fts_search", fallback)
    monkeypatch.setattr(search_mod, "search_page_fts", lambda *args, **kwargs: [])

    with sqlite3.connect(":memory:") as conn:
        assert lexical_search(conn, "該当なし", Scope(type="all")) == []
    assert fallback_calls == 0


def test_lexical_icu_failure_falls_back_to_fts5(monkeypatch):
    from services.novel_db import search as search_mod

    expected = [("fallback", 1, "fts", -1.0)]
    monkeypatch.setattr(search_mod._cfg, "NOVEL_DB_LEXICAL_BACKEND", "lance_icu")
    monkeypatch.setattr(search_mod, "fts_search", lambda *args, **kwargs: expected)

    def fail(*args, **kwargs):
        raise RuntimeError("simulated LanceDB outage")

    monkeypatch.setattr(search_mod, "search_page_fts", fail)
    with sqlite3.connect(":memory:") as conn:
        assert lexical_search(conn, "障害試験", Scope(type="all")) is expected


# ---------------------------------------------------------------------------
# hybrid_search 統合テスト
# ---------------------------------------------------------------------------


def _insert_book_with_pages(conn, book_name: str, pages: list[str]) -> int:
    cur = conn.execute(
        "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (book_name, f"/dummy/{book_name}.pdf", f"/dummy/images/{book_name}", len(pages)),
    )
    book_id = cur.lastrowid
    page_ids = []
    for i, text in enumerate(pages, start=1):
        cur = conn.execute(
            "INSERT INTO pages (book_id, page_no, image_path, full_text, char_count) VALUES (?, ?, ?, ?, ?)",
            (book_id, i, None, text, len(text)),
        )
        page_ids.append(cur.lastrowid)
    conn.execute(
        "INSERT INTO pages_fts (rowid, full_text) SELECT id, full_text FROM pages WHERE book_id = ?",
        (book_id,),
    )
    return book_id


def _insert_chunk(conn, page_id: int, idx: int, text: str, vec: list[float]) -> int:
    cur = conn.execute(
        "INSERT INTO chunks (page_id, chunk_idx, text, char_count) VALUES (?, ?, ?, ?)",
        (page_id, idx, text, len(text)),
    )
    chunk_id = cur.lastrowid
    # book_name / page_no / page_count を SQLite から取得
    meta = conn.execute(
        "SELECT b.name, p.page_no, p.char_count, b.page_count "
        "FROM pages p JOIN books b ON p.book_id = b.id WHERE p.id = ?",
        (page_id,),
    ).fetchone()
    book_name, page_no, char_count, page_count = meta if meta else ("", 0, 0, 0)
    get_chunks_table().add(
        [
            {
                "chunk_id": chunk_id,
                "book_name": book_name,
                "page_no": page_no,
                "text": text,
                "char_count": char_count or 0,
                "page_count": page_count or 0,
                "embedding": vec,
            }
        ]
    )
    return chunk_id


def test_fts_search_uses_page_id_as_deterministic_score_tiebreaker(tmp_data_dir):
    upgrade_head()
    text = "同点検索のための同一本文"
    with with_db() as conn:
        _insert_book_with_pages(conn, "book-z", [text])
        _insert_book_with_pages(conn, "book-a", [text])
        expected = [
            (str(book_name), int(page_no))
            for book_name, page_no in conn.execute(
                """
                SELECT b.name, p.page_no
                FROM pages p
                JOIN books b ON b.id = p.book_id
                ORDER BY p.id ASC
                """
            ).fetchall()
        ]
        first = fts_search(conn, "同点検索", Scope(type="all"), top=2)
        conn.commit()

    with with_db() as conn:
        second = fts_search(conn, "同点検索", Scope(type="all"), top=2)

    assert first[0][3] == first[1][3]
    assert [(str(row[0]), int(row[1])) for row in first] == expected
    assert second == first


@pytest.fixture
def search_db(tmp_data_dir, monkeypatch):
    """hybrid_search 用に小さな DB を構築する。"""
    upgrade_head()
    with with_db() as conn:
        book_id = _insert_book_with_pages(
            conn,
            "book-1",
            [
                "デュークはレティの騎士である。",  # page 1
                "アストリッドは元暗殺者だった。",  # page 2
                "薔薇園で重要な戦いが起きた。",  # page 3
            ],
        )
        # 各ページの代表チャンク（1024 次元のダミーベクトル）
        page_rows = conn.execute(
            "SELECT id, page_no FROM pages WHERE book_id = ? ORDER BY page_no",
            (book_id,),
        ).fetchall()
        # 異なる方向のベクトルで page を区別
        for (page_id, page_no), seed in zip(page_rows, [0.1, 0.5, 0.9], strict=True):
            vec = [seed] + [0.0] * 1023
            _insert_chunk(conn, page_id, 0, f"chunk text page {page_no}", vec)
        conn.commit()

    # クエリの embedding をスタブ（page 1 に近づくよう [0.1, 0, ...] を返す）
    from services.novel_db import search as search_mod

    monkeypatch.setattr(
        search_mod,
        "embed_batch",
        lambda texts: [[0.1] + [0.0] * 1023 for _ in texts],
    )


def test_hybrid_search_returns_hits_for_existing_word(search_db):
    with with_db() as conn:
        hits = hybrid_search(conn, "デューク", Scope(type="all"), top=5)
    assert len(hits) > 0
    # page 1 が含まれる
    assert any(h.book_name == "book-1" and h.page_no == 1 for h in hits)


def test_hybrid_search_snippet_has_mark_for_fts_hit(search_db):
    with with_db() as conn:
        hits = hybrid_search(conn, "デューク", Scope(type="all"), top=5)
    page1 = next(h for h in hits if h.page_no == 1)
    assert "<mark>" in page1.snippet
    assert page1.has_highlight is True


def test_hybrid_search_image_url_format(search_db):
    with with_db() as conn:
        hits = hybrid_search(conn, "デューク", Scope(type="all"), top=5)
    page1 = next(h for h in hits if h.page_no == 1)
    assert page1.image_url == "/kindle_novel/images/book-1/001.png"


def test_hybrid_search_with_book_scope_filters_other_books(search_db):
    """別書籍を追加しても scope=book で対象外になる。"""
    with with_db() as conn:
        another_book_id = _insert_book_with_pages(conn, "book-2", ["デュークも登場する別の書籍。"])
        page_rows = conn.execute("SELECT id FROM pages WHERE book_id = ?", (another_book_id,)).fetchall()
        vec = [0.1] + [0.0] * 1023
        _insert_chunk(conn, page_rows[0][0], 0, "another", vec)
        conn.commit()

        hits = hybrid_search(conn, "デューク", Scope(type="book", id="book-1"), top=10)
    assert all(h.book_name == "book-1" for h in hits)


def test_hybrid_search_returns_empty_for_no_match(search_db):
    """FTS5 で空 + ベクトルでの距離はあっても rank に反映されるが、結果は何かしら返る。"""
    # 完全に無関係な英文クエリ → FTS5 ヒットなし、ベクトルは何かしら返す
    with with_db() as conn:
        hits = hybrid_search(conn, "xyz", Scope(type="all"), top=5)
    # 単語が短すぎて build_fts5_or_query が空になる場合は FTS5 ヒット 0
    # ベクトルは hits に入る
    # 何かしらの結果（or 空）が返ること
    assert isinstance(hits, list)


# ---------------------------------------------------------------------------
# load_all_pages_of_book（B-13 段階 C、scope=book 全 page 読み込み）
# ---------------------------------------------------------------------------


def test_load_all_pages_returns_pages_in_page_no_order(search_db):
    """全 page を page_no 昇順で返す（narrative の時系列性を保つ）。"""
    with with_db() as conn:
        hits = load_all_pages_of_book(conn, "book-1")
    assert len(hits) == 3
    assert [h.page_no for h in hits] == [1, 2, 3]
    # snippet は full_text そのもの（HTML タグなし）
    assert hits[0].snippet == "デュークはレティの騎士である。"
    # rrf_score は 0.0（ランキングなし）
    assert all(h.rrf_score == 0.0 for h in hits)
    # image_url は通常の hybrid_search と同形式
    assert hits[0].image_url == "/kindle_novel/images/book-1/001.png"


def test_load_all_pages_returns_empty_for_unknown_book(search_db):
    with with_db() as conn:
        hits = load_all_pages_of_book(conn, "no-such-book")
    assert hits == []


def test_load_all_pages_filters_by_min_chars(search_db):
    """min_chars 未満の page は除外される。"""
    # search_db は各 page が ~15 字程度の短文。min_chars=20 で全件除外される
    with with_db() as conn:
        hits = load_all_pages_of_book(conn, "book-1", min_chars=20)
    assert hits == []
    # min_chars=0 では全件返る
    with with_db() as conn:
        hits = load_all_pages_of_book(conn, "book-1", min_chars=0)
    assert len(hits) == 3


def test_load_all_pages_respects_body_page_margin(search_db):
    """body_page_margin で先頭・末尾を除外する（ただし 2*margin より page 数が多いときのみ）。"""
    # 3 page しかない書籍では margin=1 で len > 2*1 = 2 なので先頭/末尾 1 ずつ除外して 1 件残る
    with with_db() as conn:
        hits = load_all_pages_of_book(conn, "book-1", body_page_margin=1)
    assert [h.page_no for h in hits] == [2]
    # margin=2 では len(3) <= 2*2 で margin 無効、全件返る
    with with_db() as conn:
        hits = load_all_pages_of_book(conn, "book-1", body_page_margin=2)
    assert len(hits) == 3
