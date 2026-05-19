"""UI プリファレンス（フィルター / ピン）の読み書き。

テーブル:
  - ui_filters(source PK, read_state_filter, genre_filter)
  - group_pins(source, pin_type, group_id, book_name; PK=(source,pin_type,group_id))
"""
from services.meta_db import connect


def get_prefs(source: str) -> dict:
    """ソース別のフィルター設定とピンを一括取得する。"""
    with connect() as conn:
        row = conn.execute(
            "SELECT read_state_filter, genre_filter FROM ui_filters WHERE source=?",
            (source,),
        ).fetchone()
        read_state_filter = row["read_state_filter"] if row else ""
        genre_filter = row["genre_filter"] if row else ""

        pin_rows = conn.execute(
            "SELECT pin_type, group_id, book_name FROM group_pins WHERE source=?",
            (source,),
        ).fetchall()

    series_pins: dict[str, str] = {}
    author_pins: dict[str, str] = {}
    for r in pin_rows:
        if r["pin_type"] == "series":
            series_pins[r["group_id"]] = r["book_name"]
        else:
            author_pins[r["group_id"]] = r["book_name"]

    return {
        "read_state_filter": read_state_filter,
        "genre_filter": genre_filter,
        "series_pins": series_pins,
        "author_pins": author_pins,
    }


def update_filters(
    source: str,
    *,
    read_state_filter: str | None = None,
    genre_filter: str | None = None,
) -> None:
    """フィルター設定を部分更新する（None のフィールドは変更しない）。"""
    with connect() as conn:
        existing = conn.execute(
            "SELECT read_state_filter, genre_filter FROM ui_filters WHERE source=?",
            (source,),
        ).fetchone()
        if existing:
            rsf = read_state_filter if read_state_filter is not None else existing["read_state_filter"]
            gf = genre_filter if genre_filter is not None else existing["genre_filter"]
            conn.execute(
                "UPDATE ui_filters SET read_state_filter=?, genre_filter=? WHERE source=?",
                (rsf, gf, source),
            )
        else:
            rsf = read_state_filter if read_state_filter is not None else ""
            gf = genre_filter if genre_filter is not None else ""
            conn.execute(
                "INSERT INTO ui_filters (source, read_state_filter, genre_filter) VALUES (?,?,?)",
                (source, rsf, gf),
            )


def set_pin(source: str, pin_type: str, group_id: str, book_name: str) -> None:
    """ピンを登録または上書きする。"""
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO group_pins (source, pin_type, group_id, book_name) VALUES (?,?,?,?)",
            (source, pin_type, group_id, book_name),
        )


def delete_pin(source: str, pin_type: str, group_id: str) -> None:
    """ピンを削除する（存在しない場合も成功）。"""
    with connect() as conn:
        conn.execute(
            "DELETE FROM group_pins WHERE source=? AND pin_type=? AND group_id=?",
            (source, pin_type, group_id),
        )
