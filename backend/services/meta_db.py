"""meta.db の接続・テーブル定義・JSON ファイルからの移行。

DATA_DIR はモジュールレベル変数として保持するので、テスト時は
  monkeypatch.setattr("services.meta_db.DATA_DIR", str(tmp_path))
でパスを切り替えられる。
"""
import json
import os
import sqlite3

from config import DATA_DIR  # noqa: F401 – テスト用にモジュール名前空間に公開

_CREATE_DDL = """
CREATE TABLE IF NOT EXISTS books_meta (
    source          TEXT NOT NULL,
    book_id         TEXT NOT NULL,
    authors         TEXT NOT NULL DEFAULT '[]',
    view_count      INTEGER,
    last_viewed_at  REAL,
    hidden          INTEGER,
    genre           TEXT,
    read_state      TEXT,
    series_id       TEXT,
    series_title    TEXT,
    series_index    REAL,
    volume          INTEGER,
    publisher       TEXT,
    asin            TEXT,
    isbn            TEXT,
    release_date    TEXT,
    PRIMARY KEY (source, book_id)
);

CREATE TABLE IF NOT EXISTS genres (
    source      TEXT NOT NULL,
    genre       TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source, genre)
);
"""


def _db_path() -> str:
    """DATA_DIR を呼び出し時に解決する（monkeypatch 対応）。"""
    import services.meta_db as _self
    return os.path.join(_self.DATA_DIR, "meta.db")


def connect() -> sqlite3.Connection:
    """meta.db へ接続して返す。ディレクトリは自動作成。"""
    import services.meta_db as _self
    os.makedirs(_self.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_db_path(), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(_CREATE_DDL)


def init_db() -> None:
    """テーブル作成 + JSON ファイルからの自動移行を実行する。

    アプリ起動時（lifespan）に 1 回だけ呼ぶ。
    """
    with connect() as conn:
        create_tables(conn)
        _migrate_from_json(conn)


# ---------------------------------------------------------------------------
# Row ↔ MetaEntry 変換ヘルパー
# ---------------------------------------------------------------------------

def row_to_entry(row: sqlite3.Row) -> dict:
    """SQLite の Row を MetaEntry 相当の dict に変換する。

    NotRequired フィールドは NULL の場合に省略する（保存前と同一構造を再現）。
    """
    entry: dict = {"authors": json.loads(row["authors"])}
    if row["view_count"] is not None:
        entry["view_count"] = row["view_count"]
    if row["last_viewed_at"] is not None:
        entry["last_viewed_at"] = row["last_viewed_at"]
    if row["hidden"]:
        entry["hidden"] = True
    for key in ("genre", "read_state", "series_id", "series_title",
                "publisher", "asin", "isbn", "release_date"):
        val = row[key]
        if val is not None:
            entry[key] = val
    if row["series_index"] is not None:
        entry["series_index"] = row["series_index"]
    if row["volume"] is not None:
        entry["volume"] = row["volume"]
    return entry


def entry_to_params(source: str, book_id: str, entry: dict) -> tuple:
    """MetaEntry → INSERT/REPLACE パラメータタプルに変換する。"""
    return (
        source,
        book_id,
        json.dumps(entry.get("authors", []), ensure_ascii=False),
        entry.get("view_count"),
        entry.get("last_viewed_at"),
        1 if entry.get("hidden") else None,
        entry.get("genre"),
        entry.get("read_state"),
        entry.get("series_id"),
        entry.get("series_title"),
        entry.get("series_index"),
        entry.get("volume"),
        entry.get("publisher"),
        entry.get("asin"),
        entry.get("isbn"),
        entry.get("release_date"),
    )


_UPSERT_SQL = """
INSERT OR REPLACE INTO books_meta
    (source, book_id, authors, view_count, last_viewed_at, hidden, genre,
     read_state, series_id, series_title, series_index, volume,
     publisher, asin, isbn, release_date)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def upsert_entry(conn: sqlite3.Connection, source: str, book_id: str, entry: dict) -> None:
    conn.execute(_UPSERT_SQL, entry_to_params(source, book_id, entry))


# ---------------------------------------------------------------------------
# JSON → SQLite 移行
# ---------------------------------------------------------------------------

def _migrate_from_json(conn: sqlite3.Connection) -> None:
    """data/meta/{source}/meta.json と data/genres/{source}.json が残っていれば
    SQLite へ取り込み、元ファイルを .bak にリネームする。

    既にそのソースのデータが存在する場合はスキップ（二重移行防止）。
    """
    import services.meta_db as _self
    data_dir = _self.DATA_DIR
    meta_base = os.path.join(data_dir, "meta")
    genre_dir = os.path.join(data_dir, "genres")

    try:
        from config import VALID_SOURCES
        sources = list(VALID_SOURCES)
    except Exception:
        sources = ["doujin", "comic", "novel"]

    for source in sources:
        _migrate_meta_json(conn, source, meta_base)
        _migrate_genre_json(conn, source, genre_dir)


def _migrate_meta_json(conn: sqlite3.Connection, source: str, meta_base: str) -> None:
    meta_json = os.path.join(meta_base, source, "meta.json")
    if not os.path.exists(meta_json):
        return
    count = conn.execute(
        "SELECT COUNT(*) FROM books_meta WHERE source=?", (source,)
    ).fetchone()[0]
    if count > 0:
        return
    try:
        with open(meta_json, encoding="utf-8") as f:
            data: dict = json.load(f)
        for book_id, entry in data.items():
            upsert_entry(conn, source, book_id, entry)
        conn.commit()
    except Exception:
        return
    try:
        os.rename(meta_json, meta_json + ".bak")
    except OSError:
        pass


def _migrate_genre_json(conn: sqlite3.Connection, source: str, genre_dir: str) -> None:
    genre_json = os.path.join(genre_dir, f"{source}.json")
    if not os.path.exists(genre_json):
        return
    count = conn.execute(
        "SELECT COUNT(*) FROM genres WHERE source=?", (source,)
    ).fetchone()[0]
    if count > 0:
        return
    try:
        with open(genre_json, encoding="utf-8") as f:
            genres: list[str] = json.load(f)
        for i, genre in enumerate(genres):
            conn.execute(
                "INSERT OR IGNORE INTO genres (source, genre, sort_order) VALUES (?,?,?)",
                (source, genre, i),
            )
        conn.commit()
    except Exception:
        return
    try:
        os.rename(genre_json, genre_json + ".bak")
    except OSError:
        pass
