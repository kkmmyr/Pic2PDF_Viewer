"""ジャンルリストの永続化サービス（SQLite バックエンド）。

保存先: meta.db の genres テーブル（source / genre / sort_order）
形式: 順序付き文字列リスト

ファイルが存在しない場合は meta.db の books_meta.genre を収集して初期リストを生成する
（migration 用途）。並び順は UI からの `PATCH /api/genres/reorder` で更新される。

ロック: `SourceLockManager` で source 単位に直列化。
"""

from services.meta_db import connect, create_tables
from utils.locks import SourceLockManager

_lock_manager = SourceLockManager()


def _ensure(conn) -> None:
    create_tables(conn)


def load_genres(source: str) -> list[str]:
    """genres テーブルからジャンルリストを sort_order 順に返す。

    未登録の場合は books_meta.genre を収集して初期リストを生成・保存する。
    """
    with _lock_manager.get(source):
        with connect() as conn:
            _ensure(conn)
            rows = conn.execute(
                "SELECT genre FROM genres WHERE source=? ORDER BY sort_order",
                (source,),
            ).fetchall()
            if rows:
                return [r["genre"] for r in rows]
            genres = _derive_from_meta(conn, source)
            _write_genres_unlocked(conn, source, genres)
            return genres


def save_genres(source: str, genres: list[str]) -> None:
    """ジャンルリストを genres テーブルに書き込む。"""
    with _lock_manager.get(source):
        with connect() as conn:
            _ensure(conn)
            _write_genres_unlocked(conn, source, genres)


def _derive_from_meta(conn, source: str) -> list[str]:
    """books_meta.genre を収集して名前順ソートした初期リストを返す。"""
    rows = conn.execute(
        "SELECT DISTINCT genre FROM books_meta WHERE source=? AND genre IS NOT NULL",
        (source,),
    ).fetchall()
    return sorted(r["genre"] for r in rows)


def _write_genres_unlocked(conn, source: str, genres: list[str]) -> None:
    """ロック取得済み前提でジャンルリストを上書きする。"""
    conn.execute("DELETE FROM genres WHERE source=?", (source,))
    conn.executemany(
        "INSERT INTO genres (source, genre, sort_order) VALUES (?,?,?)",
        [(source, g, i) for i, g in enumerate(genres)],
    )
