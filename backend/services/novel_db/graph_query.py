"""C-12: キャラクタ関係グラフ データ取得クエリ。

character_relations テーブルから nodes / edges を組み立てる読み取り専用モジュール。
書き込み（抽出・UPSERT）は relation_extractor.py が担う。
"""

from __future__ import annotations

import sqlite3
from typing import Any


def get_graph_for_series(
    conn: sqlite3.Connection,
    series_id: str,
    book_ids: list[int] | None = None,
) -> dict[str, Any]:
    """series_id のグラフデータを返す。

    Args:
        book_ids: 指定時はそれらの冊のみに絞り込む（冊フィルタ用）

    Returns:
        {"nodes": [...], "edges": [...]}
    """
    if book_ids is not None:
        placeholders = ",".join("?" * len(book_ids))
        rows = conn.execute(
            f"SELECT id, char_a, char_b, relation_type, weight, book_id "
            f"FROM character_relations "
            f"WHERE series_id = ? AND book_id IN ({placeholders})",
            [series_id, *book_ids],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, char_a, char_b, relation_type, weight, book_id FROM character_relations WHERE series_id = ?",
            (series_id,),
        ).fetchall()

    # ノード集合の構築（同名キャラは冊単位で別ノード）
    node_keys: dict[tuple[str, int], int] = {}
    nodes: list[dict] = []
    edges: list[dict] = []

    def _node_id(name: str, book_id: int) -> int:
        key = (name, book_id)
        if key not in node_keys:
            nid = len(node_keys)
            node_keys[key] = nid
            nodes.append({"id": nid, "label": name, "book_id": book_id})
        return node_keys[key]

    for rel_id, char_a, char_b, relation_type, weight, book_id in rows:
        nid_a = _node_id(char_a, book_id)
        nid_b = _node_id(char_b, book_id)
        edges.append(
            {
                "id": rel_id,
                "from": nid_a,
                "to": nid_b,
                "label": relation_type or "",
                "weight": weight,
            }
        )

    return {"nodes": nodes, "edges": edges}


def list_series_with_relations(conn: sqlite3.Connection) -> list[str]:
    """character_relations にデータが存在する series_id 一覧を返す。"""
    rows = conn.execute("SELECT DISTINCT series_id FROM character_relations ORDER BY series_id").fetchall()
    return [r[0] for r in rows]


def list_books_in_relation_series(
    conn: sqlite3.Connection,
    series_id: str,
) -> list[dict[str, Any]]:
    """series_id に属する書籍の id・name 一覧（グラフ内に存在するもの）。"""
    rows = conn.execute(
        "SELECT DISTINCT cr.book_id, b.name "
        "FROM character_relations cr "
        "JOIN books b ON b.id = cr.book_id "
        "WHERE cr.series_id = ? "
        "ORDER BY b.name",
        (series_id,),
    ).fetchall()
    return [{"id": bid, "name": name} for bid, name in rows]
