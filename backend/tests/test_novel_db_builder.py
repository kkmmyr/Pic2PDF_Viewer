"""services/novel_db/builder.py の統合テスト。

§4.2 以降、rebuild_from_pages / rebuild_book は pages テーブルが事前に存在する前提。
OCR ステップ（ocr_book）は GPU 依存のため本テストでは対象外。
embed_batch はモックで置き換える。
"""
import sqlite3

import pytest

from services.novel_db import builder, init_schema, with_db
from services.novel_db.embedder import EmbeddingError
from services.novel_db.lance_store import get_chunks_table


def _populate_pages(conn: sqlite3.Connection, book_name: str, texts: list[str]) -> int:
    """テスト用に books + pages を直接 INSERT し、book_id を返す。"""
    cur = conn.execute(
        "INSERT INTO books (name, pdf_path, images_dir, page_count) "
        "VALUES (?, ?, ?, ?)",
        (book_name, "", f"/images/{book_name}", len(texts)),
    )
    book_id = cur.lastrowid
    for i, text in enumerate(texts, start=1):
        conn.execute(
            "INSERT INTO pages (book_id, page_no, full_text, char_count) "
            "VALUES (?, ?, ?, ?)",
            (book_id, i, text, len(text)),
        )
    conn.execute(
        "INSERT INTO pages_fts (rowid, full_text) "
        "SELECT id, full_text FROM pages WHERE book_id = ?",
        (book_id,),
    )
    conn.commit()
    return book_id


@pytest.fixture
def novel_db_env(tmp_path, monkeypatch):
    """builder.py の KINDLE_NOVEL_IMAGES_DIR と DB パスを一時パスへ差し替える。"""
    images_dir = tmp_path / "kindle_novel" / "images"
    db_dir = tmp_path / "novel_db"
    images_dir.mkdir(parents=True)
    db_dir.mkdir(parents=True)

    db_path = db_dir / "novel.db"
    monkeypatch.setattr(builder, "KINDLE_NOVEL_IMAGES_DIR", str(images_dir))

    # LanceDB をテスト用 tmp_path にリダイレクト
    import services.novel_db.lance_store as _lance
    lance_path = str(tmp_path / "novel.lancedb")
    monkeypatch.setattr(_lance, "NOVEL_DB_LANCE_PATH", lance_path)
    _lance.reset_db()

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
        init_schema(conn)
        _populate_pages(conn, book_name, ["Page one content. Hello world."] * 3)

        builder.rebuild_from_pages(conn, book_name)

        row = conn.execute(
            "SELECT page_count FROM books WHERE name = ?", (book_name,)
        ).fetchone()
        assert row is not None
        assert row[0] == 3

        chunks_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert chunks_count > 0
    finally:
        conn.close()

    # LanceDB にも同数のチャンクが登録されている
    vec_count = get_chunks_table().count_rows()
    assert vec_count == chunks_count


def test_rebuild_from_pages_replaces_existing_chunks(novel_db_env, monkeypatch):
    book_name = "test-book-replace"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        init_schema(conn)
        _populate_pages(conn, book_name, ["First version content here, enough text."])
        builder.rebuild_from_pages(conn, book_name)
        first_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert first_chunks > 0

    # pages の full_text を直接 UPDATE して再構築
    with with_db(str(novel_db_env["db_path"])) as conn:
        conn.execute(
            "UPDATE pages SET full_text = ?, char_count = ? "
            "WHERE book_id = (SELECT id FROM books WHERE name = ?)",
            ("Second version content with different text.", 44, book_name),
        )
        conn.commit()
        builder.rebuild_from_pages(conn, book_name)

        # books 行は 1 件のみ（重複なし）
        rows = conn.execute(
            "SELECT COUNT(*) FROM books WHERE name = ?", (book_name,)
        ).fetchall()
        assert rows[0][0] == 1

        # chunks は前回分が消えて再構築されている
        second_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert second_chunks > 0


def test_rebuild_from_pages_rolls_back_chunks_on_embedding_failure(novel_db_env, monkeypatch):
    book_name = "test-book-fail"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch_failing)

    with with_db(str(novel_db_env["db_path"])) as conn:
        init_schema(conn)
        _populate_pages(
            conn, book_name, ["Some content for failing embedding test." * 3]
        )
        with pytest.raises(EmbeddingError):
            builder.rebuild_from_pages(conn, book_name)

        # books/pages は残る（OCR 済みデータは保持）
        assert conn.execute(
            "SELECT COUNT(*) FROM books WHERE name = ?", (book_name,)
        ).fetchone()[0] == 1
        # chunks はロールバックされて 0 件
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0


def test_rebuild_from_pages_raises_when_book_not_in_db(novel_db_env):
    with with_db(str(novel_db_env["db_path"])) as conn:
        init_schema(conn)
        with pytest.raises(ValueError, match="run OCR first"):
            builder.rebuild_from_pages(conn, "nonexistent-book")


def test_rebuild_book_alias_works(novel_db_env, monkeypatch):
    """rebuild_book() は rebuild_from_pages() への後方互換エイリアスであることを確認。"""
    book_name = "test-alias"
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        init_schema(conn)
        _populate_pages(conn, book_name, ["Alias test content here, enough chars."])
        builder.rebuild_book(conn, book_name)

        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] > 0
