"""services/novel_db/search.py:search_book_summaries の単体テスト。

embedder 呼び出しはモック。スキーマ初期化 + book_summaries_vec への手動 INSERT で
検証する。
"""
from unittest.mock import patch

from services.novel_db import init_schema, with_db
from services.novel_db.lance_store import get_summaries_table
from services.novel_db.search import Scope, search_book_summaries


def _setup_books(conn, books: list[tuple[str, list[float]]]) -> list[int]:
    """books と LanceDB summaries テーブルに書籍を投入し、ID リストを返す。"""
    ids = []
    table = get_summaries_table()
    for name, vec in books:
        cur = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count, indexed_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (name, f"/{name}.pdf", "/imgs", 100),
        )
        bid = cur.lastrowid
        table.add([{"book_id": bid, "book_name": name, "embedding": vec}])
        ids.append(bid)
    conn.commit()
    return ids


def _vec(ones_at: int, dim: int = 1024) -> list[float]:
    """指定の index だけ 1.0、他は 0.0 のベクトル（コサイン類似度の検証に使う）。"""
    v = [0.0] * dim
    v[ones_at] = 1.0
    return v


def test_search_book_summaries_returns_nearest_first(tmp_data_dir):
    """クエリ ベクトルに最も近い書籍が distance 昇順で先頭に来る。"""
    with with_db() as conn:
        init_schema(conn)
        _setup_books(conn, [
            ("a", _vec(0)),
            ("b", _vec(1)),
            ("c", _vec(2)),
        ])

        with patch("services.novel_db.search.embed_batch") as mock_embed:
            mock_embed.return_value = [_vec(1)]  # b に近い
            results = search_book_summaries(conn, "質問", Scope("all"), top=3)

    assert len(results) == 3
    assert results[0][0] == "b"  # 完全一致が先頭
    # distance は昇順
    assert results[0][1] <= results[1][1] <= results[2][1]


def test_search_book_summaries_respects_scope_book(tmp_data_dir):
    """scope=book なら指定書籍だけ返る。"""
    with with_db() as conn:
        init_schema(conn)
        _setup_books(conn, [("a", _vec(0)), ("b", _vec(1))])

        with patch("services.novel_db.search.embed_batch") as mock_embed:
            mock_embed.return_value = [_vec(0)]
            results = search_book_summaries(conn, "Q", Scope("book", "b"), top=5)

    assert [name for name, _ in results] == ["b"]


def test_search_book_summaries_returns_empty_for_unknown_scope(tmp_data_dir):
    with with_db() as conn:
        init_schema(conn)
        _setup_books(conn, [("a", _vec(0))])

        with patch("services.novel_db.search.embed_batch") as mock_embed:
            mock_embed.return_value = [_vec(0)]
            results = search_book_summaries(
                conn, "Q", Scope("book", "no-such"), top=5,
            )
    assert results == []


def test_search_book_summaries_handles_empty_table(tmp_data_dir):
    """LanceDB summaries テーブルが空のときは空リストを返す。"""
    with with_db() as conn:
        init_schema(conn)
        # テーブルは作成されるがデータなし
        results = search_book_summaries(conn, "Q", Scope("all"), top=5)

    assert results == []


def test_search_book_summaries_top_limits_count(tmp_data_dir):
    with with_db() as conn:
        init_schema(conn)
        _setup_books(conn, [(f"b{i}", _vec(i)) for i in range(5)])

        with patch("services.novel_db.search.embed_batch") as mock_embed:
            mock_embed.return_value = [_vec(0)]
            results = search_book_summaries(conn, "Q", Scope("all"), top=2)

    assert len(results) == 2
