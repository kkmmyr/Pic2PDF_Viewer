"""services/novel_db/builder.py の統合テスト。

§4.2 以降、rebuild_from_pages / rebuild_book は pages テーブルが事前に存在する前提。
OCR ステップ（ocr_book）は GPU 依存のため本テストでは対象外。
embed_batch はモックで置き換える。
"""

import sqlite3

import pytest
from fastapi import HTTPException

from services.novel_db import builder, page_index_builder, with_db
from services.novel_db.embedder import EmbeddingError
from services.novel_db.lance_store import get_chunks_table
from services.novel_db.migrations import upgrade_head


@pytest.mark.parametrize("book_name", ["../outside", "C:/Windows", "folder/book"])
def test_resolve_images_dir_rejects_unsafe_book_name(tmp_data_dir, book_name):
    with pytest.raises(HTTPException):
        builder._resolve_images_dir(book_name)


def _populate_pages(conn: sqlite3.Connection, book_name: str, texts: list[str]) -> int:
    """テスト用に books + pages を直接 INSERT し、book_id を返す。"""
    cur = conn.execute(
        "INSERT INTO books (name, pdf_path, images_dir, page_count) VALUES (?, ?, ?, ?)",
        (book_name, "", f"/images/{book_name}", len(texts)),
    )
    book_id = cur.lastrowid
    for i, text in enumerate(texts, start=1):
        conn.execute(
            "INSERT INTO pages (book_id, page_no, full_text, char_count) VALUES (?, ?, ?, ?)",
            (book_id, i, text, len(text)),
        )
    conn.execute(
        "INSERT INTO pages_fts (rowid, full_text) SELECT id, full_text FROM pages WHERE book_id = ?",
        (book_id,),
    )
    conn.commit()
    return book_id


@pytest.fixture
def novel_db_env(tmp_path, monkeypatch):
    """config.KINDLE_NOVEL_IMAGES_DIR と DB パスを一時パスへ差し替える。"""
    images_dir = tmp_path / "kindle_novel" / "images"
    db_dir = tmp_path / "novel_db"
    images_dir.mkdir(parents=True)
    db_dir.mkdir(parents=True)

    import config

    db_path = db_dir / "novel.db"
    monkeypatch.setattr(config, "KINDLE_NOVEL_IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(config, "NOVEL_DB_DIR", str(db_dir))
    monkeypatch.setattr(config, "NOVEL_DB_PATH", str(db_path))

    # settings オブジェクトを差し替え（app_settings.NOVEL_DB_DIR / novel_db_settings.NOVEL_DB_LANCE_PATH）
    from config import app_settings
    from config.novel_db import novel_db_settings

    monkeypatch.setattr(app_settings, "NOVEL_DB_DIR", db_dir)
    lance_path = str(tmp_path / "novel.lancedb")
    monkeypatch.setattr(novel_db_settings, "NOVEL_DB_LANCE_PATH", lance_path)

    # LanceDB グローバル接続をリセット（テスト用 tmp_path に再接続させる）
    import services.novel_db.lance_store as _lance

    _lance.reset_db()

    upgrade_head()
    return {"images_dir": images_dir, "db_path": db_path}


def _stub_embed_batch(texts: list[str]) -> list[list[float]]:
    return [[0.01 * (i + 1)] * 1024 for i in range(len(texts))]


def _stub_embed_batch_failing(texts: list[str]) -> list[list[float]]:
    raise EmbeddingError("simulated network error")


def test_rebuild_from_pages_creates_chunks(novel_db_env, monkeypatch):
    book_name = "test-book-1"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)

    conn = sqlite3.connect(str(novel_db_env["db_path"]))
    try:
        _populate_pages(conn, book_name, ["Page one content. Hello world."] * 3)

        builder.rebuild_from_pages(conn, book_name)

        row = conn.execute("SELECT page_count FROM books WHERE name = ?", (book_name,)).fetchone()
        assert row is not None
        assert row[0] == 3

        chunks_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert chunks_count > 0
    finally:
        conn.close()

    # LanceDB にも同数のチャンクが登録されている
    vec_count = get_chunks_table().count_rows()
    assert vec_count == chunks_count


def test_rebuild_from_pages_excludes_non_narrative_pages(novel_db_env, monkeypatch):
    book_name = "test-page-types"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        book_id = _populate_pages(
            conn,
            book_name,
            ["Narrative content long enough for a chunk.", "Table of contents should not be indexed."],
        )
        conn.execute(
            "UPDATE pages SET page_type='toc', index_eligible=0 WHERE book_id=? AND page_no=2",
            (book_id,),
        )
        conn.commit()
        builder.rebuild_from_pages(conn, book_name)

        indexed_pages = conn.execute(
            "SELECT p.page_no FROM chunks c JOIN pages p ON p.id=c.page_id ORDER BY p.page_no"
        ).fetchall()
        assert {row[0] for row in indexed_pages} == {1}


def test_rebuild_from_pages_replaces_existing_chunks(novel_db_env, monkeypatch):
    book_name = "test-book-replace"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        _populate_pages(conn, book_name, ["First version content here, enough text."])
        builder.rebuild_from_pages(conn, book_name)
        first_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert first_chunks > 0

    # pages の full_text を直接 UPDATE して再構築
    with with_db(str(novel_db_env["db_path"])) as conn:
        conn.execute(
            "UPDATE pages SET full_text = ?, char_count = ? WHERE book_id = (SELECT id FROM books WHERE name = ?)",
            ("Second version content with different text.", 44, book_name),
        )
        conn.commit()
        builder.rebuild_from_pages(conn, book_name)

        # books 行は 1 件のみ（重複なし）
        rows = conn.execute("SELECT COUNT(*) FROM books WHERE name = ?", (book_name,)).fetchall()
        assert rows[0][0] == 1

        # chunks は前回分が消えて再構築されている
        second_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert second_chunks > 0


def test_rebuild_from_pages_rolls_back_chunks_on_embedding_failure(novel_db_env, monkeypatch):
    book_name = "test-book-fail"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch_failing)

    with with_db(str(novel_db_env["db_path"])) as conn:
        _populate_pages(conn, book_name, ["Some content for failing embedding test." * 3])
        with pytest.raises(EmbeddingError):
            builder.rebuild_from_pages(conn, book_name)

        # books/pages は残る（OCR 済みデータは保持）
        assert conn.execute("SELECT COUNT(*) FROM books WHERE name = ?", (book_name,)).fetchone()[0] == 1
        # chunks はロールバックされて 0 件
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0


def test_rebuild_from_pages_raises_when_book_not_in_db(novel_db_env):
    with with_db(str(novel_db_env["db_path"])) as conn:
        with pytest.raises(ValueError, match="run OCR first"):
            builder.rebuild_from_pages(conn, "nonexistent-book")


def test_rebuild_book_alias_works(novel_db_env, monkeypatch):
    """rebuild_book() は rebuild_from_pages() への後方互換エイリアスであることを確認。"""
    book_name = "test-alias"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        _populate_pages(conn, book_name, ["Alias test content here, enough chars."])
        builder.rebuild_book(conn, book_name)

        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] > 0


def _lance_rows() -> list[dict]:
    return get_chunks_table().search().limit(100).to_list()


def test_rebuild_page_changes_only_target_page_and_refreshes_fts(novel_db_env, monkeypatch):
    book_name = "test-page-rebuild"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)
    monkeypatch.setattr(page_index_builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        book_id = _populate_pages(
            conn,
            book_name,
            [
                "obsoletekeyword remains in the first narrative page long enough.",
                "stablekeyword remains in the second narrative page long enough.",
            ],
        )
        builder.rebuild_from_pages(conn, book_name)
        stable_before = conn.execute(
            "SELECT c.id, c.text FROM chunks c JOIN pages p ON p.id=c.page_id WHERE p.book_id=? AND p.page_no=2",
            (book_id,),
        ).fetchall()
        stable_lance_before = sorted(
            (int(row["chunk_id"]), str(row["text"])) for row in _lance_rows() if int(row["page_no"]) == 2
        )

        new_text = "freshkeyword replaces the first narrative page and is long enough."
        conn.execute(
            "UPDATE pages SET full_text=?, char_count=? WHERE book_id=? AND page_no=1",
            (new_text, len(new_text), book_id),
        )
        conn.commit()
        page_index_builder.rebuild_page_from_pages(conn, book_name, 1)

        stable_after = conn.execute(
            "SELECT c.id, c.text FROM chunks c JOIN pages p ON p.id=c.page_id WHERE p.book_id=? AND p.page_no=2",
            (book_id,),
        ).fetchall()
        stable_lance_after = sorted(
            (int(row["chunk_id"]), str(row["text"])) for row in _lance_rows() if int(row["page_no"]) == 2
        )
        assert stable_after == stable_before
        assert stable_lance_after == stable_lance_before
        assert conn.execute("SELECT COUNT(*) FROM pages_fts WHERE pages_fts MATCH 'freshkeyword'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM pages_fts WHERE pages_fts MATCH 'obsoletekeyword'").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT indexed_at FROM books WHERE id=?",
                (book_id,),
            ).fetchone()[0]
            is not None
        )


def test_rebuild_page_removes_chunks_for_non_indexable_page(novel_db_env, monkeypatch):
    book_name = "test-page-excluded"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)
    monkeypatch.setattr(page_index_builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        book_id = _populate_pages(
            conn,
            book_name,
            [
                "This narrative page initially has a searchable chunk.",
                "This second page remains indexed and unchanged throughout.",
            ],
        )
        builder.rebuild_from_pages(conn, book_name)
        conn.execute(
            "UPDATE pages SET page_type='advertisement', index_eligible=0 WHERE book_id=? AND page_no=1",
            (book_id,),
        )
        conn.commit()

        page_index_builder.rebuild_page_from_pages(conn, book_name, 1)

        indexed_pages = conn.execute(
            "SELECT p.page_no FROM chunks c JOIN pages p ON p.id=c.page_id WHERE p.book_id=? ORDER BY p.page_no",
            (book_id,),
        ).fetchall()
        assert [int(row[0]) for row in indexed_pages] == [2]
        assert {int(row["page_no"]) for row in _lance_rows()} == {2}


def test_rebuild_page_embedding_failure_does_not_mutate_existing_index(novel_db_env, monkeypatch):
    book_name = "test-page-precompute-fail"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        book_id = _populate_pages(
            conn,
            book_name,
            ["Original indexed page content is long enough for one chunk."],
        )
        builder.rebuild_from_pages(conn, book_name)
        chunks_before = conn.execute("SELECT id, text FROM chunks ORDER BY id").fetchall()
        lance_before = sorted((int(row["chunk_id"]), str(row["text"])) for row in _lance_rows())
        indexed_at_before = conn.execute(
            "SELECT indexed_at FROM books WHERE id=?",
            (book_id,),
        ).fetchone()[0]

        new_text = "Changed page content would require a new embedding calculation."
        conn.execute(
            "UPDATE pages SET full_text=?, char_count=? WHERE book_id=? AND page_no=1",
            (new_text, len(new_text), book_id),
        )
        conn.commit()
        monkeypatch.setattr(page_index_builder, "embed_batch", _stub_embed_batch_failing)

        with pytest.raises(EmbeddingError):
            page_index_builder.rebuild_page_from_pages(conn, book_name, 1)

        assert conn.execute("SELECT id, text FROM chunks ORDER BY id").fetchall() == chunks_before
        assert sorted((int(row["chunk_id"]), str(row["text"])) for row in _lance_rows()) == lance_before
        assert (
            conn.execute(
                "SELECT indexed_at FROM books WHERE id=?",
                (book_id,),
            ).fetchone()[0]
            == indexed_at_before
        )


def test_rebuild_page_restores_lance_rows_when_add_fails(novel_db_env, monkeypatch):
    book_name = "test-page-lance-fail"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)
    monkeypatch.setattr(page_index_builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        book_id = _populate_pages(
            conn,
            book_name,
            ["Original page content is long enough to preserve during rollback."],
        )
        builder.rebuild_from_pages(conn, book_name)
        chunks_before = conn.execute("SELECT id, text FROM chunks ORDER BY id").fetchall()
        lance_before = sorted((int(row["chunk_id"]), str(row["text"])) for row in _lance_rows())

        new_text = "Replacement page content triggers a simulated LanceDB add failure."
        conn.execute(
            "UPDATE pages SET full_text=?, char_count=? WHERE book_id=? AND page_no=1",
            (new_text, len(new_text), book_id),
        )
        conn.commit()

        real_table = get_chunks_table()

        class FailOnceTable:
            def __init__(self):
                self.add_calls = 0

            def search(self):
                return real_table.search()

            def delete(self, predicate):
                return real_table.delete(predicate)

            def add(self, rows):
                self.add_calls += 1
                if self.add_calls == 1:
                    raise RuntimeError("simulated LanceDB add failure")
                return real_table.add(rows)

        monkeypatch.setattr(
            page_index_builder,
            "get_chunks_table",
            lambda: FailOnceTable(),
        )

        with pytest.raises(RuntimeError, match="simulated LanceDB add failure"):
            page_index_builder.rebuild_page_from_pages(conn, book_name, 1)

        assert conn.execute("SELECT id, text FROM chunks ORDER BY id").fetchall() == chunks_before
        assert sorted((int(row["chunk_id"]), str(row["text"])) for row in _lance_rows()) == lance_before
        assert (
            conn.execute(
                "SELECT indexed_at FROM books WHERE id=?",
                (book_id,),
            ).fetchone()[0]
            is None
        )
