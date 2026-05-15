"""services/meta_db.py のユニットテスト。"""
import json
import os
import sqlite3

import pytest

import services.meta_db as meta_db_module
from services.meta_db import (
    connect,
    create_tables,
    entry_to_params,
    row_to_entry,
    upsert_entry,
)


@pytest.fixture(autouse=True)
def patch_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("services.meta_db.DATA_DIR", str(tmp_path))


# ---------------------------------------------------------------------------
# connect / create_tables
# ---------------------------------------------------------------------------

class TestConnect:
    def test_接続でディレクトリが自動作成される(self, tmp_path):
        sub = tmp_path / "sub"
        import services.meta_db as m
        m.DATA_DIR = str(sub)
        conn = connect()
        conn.close()
        assert (sub / "meta.db").exists()

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


# ---------------------------------------------------------------------------
# _migrate_from_json
# ---------------------------------------------------------------------------

class TestMigrateFromJson:
    def _make_meta_json(self, tmp_path, source: str, data: dict) -> None:
        meta_dir = tmp_path / "meta" / source
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "meta.json").write_text(json.dumps(data), encoding="utf-8")

    def _make_genre_json(self, tmp_path, source: str, genres: list) -> None:
        genre_dir = tmp_path / "genres"
        genre_dir.mkdir(exist_ok=True)
        (genre_dir / f"{source}.json").write_text(json.dumps(genres), encoding="utf-8")

    def test_meta_jsonからデータが移行される(self, tmp_path):
        self._make_meta_json(tmp_path, "novel", {
            "book1.pdf": {"authors": ["著者A"], "view_count": 3},
        })
        from services.meta_db import init_db
        init_db()
        conn = connect()
        count = conn.execute(
            "SELECT COUNT(*) FROM books_meta WHERE source='novel'"
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_移行後にbakファイルが作成される(self, tmp_path):
        self._make_meta_json(tmp_path, "novel", {"book.pdf": {"authors": []}})
        from services.meta_db import init_db
        init_db()
        bak = tmp_path / "meta" / "novel" / "meta.json.bak"
        assert bak.exists()

    def test_データが既にある場合は移行をスキップする(self, tmp_path):
        self._make_meta_json(tmp_path, "novel", {"book1.pdf": {"authors": ["著者A"]}})
        from services.meta_db import init_db
        init_db()
        # 2回目（データあり）でも壊れない
        self._make_meta_json(tmp_path, "novel", {"book2.pdf": {"authors": ["著者B"]}})
        init_db()
        conn = connect()
        count = conn.execute(
            "SELECT COUNT(*) FROM books_meta WHERE source='novel'"
        ).fetchone()[0]
        conn.close()
        assert count == 1  # 2回目はスキップされるので追加されない

    def test_genre_jsonからジャンルが移行される(self, tmp_path):
        self._make_genre_json(tmp_path, "novel", ["ファンタジー", "SF"])
        from services.meta_db import init_db
        init_db()
        conn = connect()
        count = conn.execute(
            "SELECT COUNT(*) FROM genres WHERE source='novel'"
        ).fetchone()[0]
        conn.close()
        assert count == 2

    def test_jsonが存在しない場合はスキップされる(self):
        from services.meta_db import init_db
        init_db()  # meta.json / genres.json なし → エラーなし
