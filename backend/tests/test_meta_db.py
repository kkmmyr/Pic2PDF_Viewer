"""services/meta_db.py のユニットテスト。"""
import json
import sqlite3

import pytest

from services.meta_db import (
    connect,
    create_tables,
    row_to_entry,
    upsert_entry,
)


@pytest.fixture(autouse=True)
def patch_data_dir(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path))


# ---------------------------------------------------------------------------
# connect / create_tables
# ---------------------------------------------------------------------------

class TestConnect:
    def test_接続でディレクトリが自動作成される(self, tmp_path, monkeypatch):
        sub = tmp_path / "sub"
        import config
        monkeypatch.setattr(config, "META_DB_DIR", str(sub))
        conn = connect()
        conn.close()
        assert (sub / "meta2.db").exists()

    def test_接続後にテーブルを作成できる(self):
        conn = connect()
        create_tables(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "books_meta" in tables
        assert "genres" in tables
        conn.close()

    def test_create_tablesは冪等である(self):
        conn = connect()
        create_tables(conn)
        create_tables(conn)  # 2回呼んでもエラーにならない
        conn.close()


# ---------------------------------------------------------------------------
# entry_to_params / row_to_entry
# ---------------------------------------------------------------------------

class TestEntryConversion:
    def _setup_conn(self) -> sqlite3.Connection:
        conn = connect()
        create_tables(conn)
        return conn

    def test_full_entryの往復変換(self):
        entry = {
            "authors": ["著者A", "著者B"],
            "view_count": 5,
            "last_viewed_at": 1234567890.0,
            "hidden": True,
            "genre": "ファンタジー",
            "read_state": "done",
            "series_id": "series1",
            "series_title": "テストシリーズ",
            "series_index": 2.0,
            "volume": 2,
            "publisher": "出版社X",
            "asin": "B001234567",
            "isbn": "978-4-1234-5678-9",
            "release_date": "2024-01-01",
        }
        conn = self._setup_conn()
        upsert_entry(conn, "novel", "book1.pdf", entry)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM books_meta WHERE source=? AND book_id=?",
            ("novel", "book1.pdf"),
        ).fetchone()
        result = row_to_entry(row)
        conn.close()

        assert result["authors"] == ["著者A", "著者B"]
        assert result["view_count"] == 5
        assert result["hidden"] is True
        assert result["genre"] == "ファンタジー"
        assert result["asin"] == "B001234567"

    def test_NULLフィールドは省略される(self):
        conn = self._setup_conn()
        upsert_entry(conn, "novel", "book2.pdf", {"authors": []})
        conn.commit()
        row = conn.execute(
            "SELECT * FROM books_meta WHERE source=? AND book_id=?",
            ("novel", "book2.pdf"),
        ).fetchone()
        result = row_to_entry(row)
        conn.close()

        assert "view_count" not in result
        assert "hidden" not in result
        assert "genre" not in result

    def test_hidden_falseはエントリに含まれない(self):
        conn = self._setup_conn()
        upsert_entry(conn, "novel", "book3.pdf", {"authors": [], "hidden": False})
        conn.commit()
        row = conn.execute(
            "SELECT * FROM books_meta WHERE source=? AND book_id=?",
            ("novel", "book3.pdf"),
        ).fetchone()
        result = row_to_entry(row)
        conn.close()
        assert "hidden" not in result


# ---------------------------------------------------------------------------
# upsert_entry（UPSERT = INSERT OR REPLACE）
# ---------------------------------------------------------------------------

class TestUpsertEntry:
    def _setup_conn(self) -> sqlite3.Connection:
        conn = connect()
        create_tables(conn)
        return conn

    def test_新規挿入が成功する(self):
        conn = self._setup_conn()
        upsert_entry(conn, "novel", "new_book.pdf", {"authors": ["著者"]})
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM books_meta WHERE source='novel' AND book_id='new_book.pdf'"
        ).fetchone()[0]
        assert count == 1
        conn.close()

    def test_既存エントリを上書きする(self):
        conn = self._setup_conn()
        upsert_entry(conn, "novel", "book.pdf", {"authors": ["旧著者"]})
        conn.commit()
        upsert_entry(conn, "novel", "book.pdf", {"authors": ["新著者"]})
        conn.commit()
        row = conn.execute(
            "SELECT authors FROM books_meta WHERE source='novel' AND book_id='book.pdf'"
        ).fetchone()
        assert json.loads(row["authors"]) == ["新著者"]
        conn.close()

    def test_異なるsourceは別レコードとして扱われる(self):
        conn = self._setup_conn()
        upsert_entry(conn, "novel", "book.pdf", {"authors": ["A"]})
        upsert_entry(conn, "comic", "book.pdf", {"authors": ["B"]})
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM books_meta").fetchone()[0]
        assert count == 2
        conn.close()
