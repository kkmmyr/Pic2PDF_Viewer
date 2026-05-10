"""services/novel_db/builder.py の統合テスト。

Ollama 呼び出し（embed_batch）はモックで置き換える。
"""
import os
import sqlite3
from pathlib import Path

import fitz
import pytest

from services.novel_db import builder, init_schema, with_db
from services.novel_db.embedder import EmbeddingError


def _make_text_pdf(path: Path, pages_text: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page(width=400, height=600)
        page.insert_text((50, 50), text)
    doc.save(str(path))
    doc.close()


@pytest.fixture
def novel_db_env(tmp_path, monkeypatch):
    """builder.py が参照する PDF ディレクトリと DB を一時パスへ差し替える。"""
    pdf_dir = tmp_path / "kindle_novel" / "pdfs"
    images_dir = tmp_path / "kindle_novel" / "images"
    db_dir = tmp_path / "novel_db"
    pdf_dir.mkdir(parents=True)
    images_dir.mkdir(parents=True)
    db_dir.mkdir(parents=True)

    db_path = db_dir / "novel.db"

    # builder モジュール内で使われる定数を差し替え
    monkeypatch.setattr(builder, "KINDLE_NOVEL_PDF_DIR", str(pdf_dir))
    monkeypatch.setattr(builder, "KINDLE_NOVEL_IMAGES_DIR", str(images_dir))

    return {
        "pdf_dir": pdf_dir,
        "images_dir": images_dir,
        "db_path": db_path,
    }


def _stub_embed_batch(texts: list[str]) -> list[list[float]]:
    """1024 次元のダミー embedding を返す。"""
    return [[0.01 * (i + 1)] * 1024 for i in range(len(texts))]


def _stub_embed_batch_failing(texts: list[str]) -> list[list[float]]:
    raise EmbeddingError("simulated network error")


def test_rebuild_book_creates_records(novel_db_env, monkeypatch):
    book_name = "test-book-1"
    pdf_path = novel_db_env["pdf_dir"] / f"{book_name}.pdf"
    _make_text_pdf(pdf_path, ["Page one content. Hello world."] * 3)

    # embedding は外部依存なのでスタブ
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)

    conn = sqlite3.connect(str(novel_db_env["db_path"]))
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        init_schema(conn)
        builder.rebuild_book(conn, book_name)

        # 検証
        row = conn.execute(
            "SELECT id, page_count FROM books WHERE name = ?", (book_name,)
        ).fetchone()
        assert row is not None
        book_id, page_count = row
        assert page_count == 3

        page_rows = conn.execute(
            "SELECT page_no FROM pages WHERE book_id = ? ORDER BY page_no", (book_id,)
        ).fetchall()
        assert [r[0] for r in page_rows] == [1, 2, 3]

        # FTS5 同期
        fts_count = conn.execute(
            "SELECT COUNT(*) FROM pages_fts"
        ).fetchone()[0]
        assert fts_count == 3

        # chunks
        chunks_count = conn.execute(
            "SELECT COUNT(*) FROM chunks"
        ).fetchone()[0]
        assert chunks_count > 0

        # chunks_vec
        vec_count = conn.execute(
            "SELECT COUNT(*) FROM chunks_vec"
        ).fetchone()[0]
        assert vec_count == chunks_count
    finally:
        conn.close()


def test_rebuild_book_replaces_existing_records(novel_db_env, monkeypatch):
    book_name = "test-book-replace"
    pdf_path = novel_db_env["pdf_dir"] / f"{book_name}.pdf"
    _make_text_pdf(pdf_path, ["First version content here."])

    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        init_schema(conn)
        builder.rebuild_book(conn, book_name)
        first_text = conn.execute(
            "SELECT full_text FROM pages "
            "WHERE book_id = (SELECT id FROM books WHERE name = ?)",
            (book_name,),
        ).fetchone()[0]
        assert "First" in first_text

    # 同じ書籍をもう一度構築（テキストを変える + ページ数を変える）
    _make_text_pdf(pdf_path, ["Second version content with different text."] * 2)
    with with_db(str(novel_db_env["db_path"])) as conn:
        builder.rebuild_book(conn, book_name)

        # 既存レコードは削除されて 1 行だけ残る（重複なし）
        rows = conn.execute(
            "SELECT page_count FROM books WHERE name = ?", (book_name,)
        ).fetchall()
        assert len(rows) == 1, "duplicate books row after rebuild"
        assert rows[0][0] == 2

        # 新しいテキストに置き換わっていること（First が消えて Second になっている）
        page_texts = conn.execute(
            "SELECT full_text FROM pages "
            "WHERE book_id = (SELECT id FROM books WHERE name = ?)",
            (book_name,),
        ).fetchall()
        assert len(page_texts) == 2
        for (txt,) in page_texts:
            assert "Second" in txt
            assert "First" not in txt


def test_rebuild_book_rolls_back_on_embedding_failure(novel_db_env, monkeypatch):
    book_name = "test-book-fail"
    pdf_path = novel_db_env["pdf_dir"] / f"{book_name}.pdf"
    _make_text_pdf(pdf_path, ["Some content for failing embedding test." * 3])

    # embedding を失敗させる
    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch_failing)

    with with_db(str(novel_db_env["db_path"])) as conn:
        init_schema(conn)
        with pytest.raises(EmbeddingError):
            builder.rebuild_book(conn, book_name)

        # books レコードがロールバックされていること（書籍未構築状態に戻っている）
        row = conn.execute(
            "SELECT COUNT(*) FROM books WHERE name = ?", (book_name,)
        ).fetchone()
        assert row[0] == 0


def test_rebuild_book_raises_on_missing_pdf(novel_db_env):
    with with_db(str(novel_db_env["db_path"])) as conn:
        init_schema(conn)
        with pytest.raises(FileNotFoundError):
            builder.rebuild_book(conn, "nonexistent-book")


def test_rebuild_book_records_image_path_when_image_exists(novel_db_env, monkeypatch):
    book_name = "test-book-with-image"
    pdf_path = novel_db_env["pdf_dir"] / f"{book_name}.pdf"
    _make_text_pdf(pdf_path, ["First page text content."])

    # 1 ページ目に対応する画像を配置
    book_images_dir = novel_db_env["images_dir"] / book_name
    book_images_dir.mkdir()
    img_path = book_images_dir / "001.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 100)  # 形式チェックは存在のみ

    monkeypatch.setattr(builder, "embed_batch", _stub_embed_batch)

    with with_db(str(novel_db_env["db_path"])) as conn:
        init_schema(conn)
        builder.rebuild_book(conn, book_name)

        page_image = conn.execute(
            "SELECT image_path FROM pages "
            "WHERE book_id = (SELECT id FROM books WHERE name = ?) AND page_no = 1",
            (book_name,),
        ).fetchone()[0]
        assert page_image is not None
        assert os.path.basename(page_image) == "001.png"
