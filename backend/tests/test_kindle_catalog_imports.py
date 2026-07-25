"""Amazon 注文 CSV 差分取り込みテスト。"""

from pathlib import Path

import config
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.imports import run_orders_import
from services.kindle_catalog.migrations import upgrade_head
from services.kindle_catalog.repository import list_books, stats


def _write_csvs(root: Path) -> None:
    orders = root / "amazon-order" / "Your Amazon Orders"
    orders.mkdir(parents=True)
    (orders / "Digital Content Orders.csv").write_text(
        "\n".join(
            [
                "ASIN,Order ID,Order Date,Product Name,Digital Order Item ID,Price,Order Status,Seller of Record",
                "B000ORDER1,ORDER-1,2026-07-01T00:00:00Z,注文作品,ITEM-1,¥500,SUCCESS,出版社",
            ]
        ),
        encoding="utf-8-sig",
    )
    (orders / "Digital Borrowed Items.csv").write_text(
        "\n".join(
            [
                "ASIN,Loan Creation Date,Loan Status,Product Name,Author,Loan Program,Loan Acceptance Date,End Date",
                "B000BORROW,2026-07-02T00:00:00Z,ACTIVE,借用作品,著者A,Kindle Unlimited,2026-07-02T00:00:01Z,",
            ]
        ),
        encoding="utf-8",
    )
    (orders / "Digital Returns.csv").write_text(
        "\n".join(
            [
                "ASIN,Return Date,Product Name,Order ID,Processing Successful,Amount Refunded,Return Status",
                "B000ORDER1,2026-07-03T00:00:00Z,注文作品,ORDER-1,Yes,¥500,Completed",
            ]
        ),
        encoding="utf-8",
    )


def test_orders_import_is_idempotent_and_does_not_store_payment_data(tmp_path, monkeypatch):
    source = tmp_path / "amazon"
    _write_csvs(source)
    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path / "target"))
    monkeypatch.setattr(config, "AMAZON_DATA_DIR", str(source))
    upgrade_head()

    first = run_orders_import()
    second = run_orders_import()

    assert first["files_processed"] == 3
    assert first["records_processed"] == 3
    assert second["files_processed"] == 0
    assert second["files_skipped"] == 3
    summary = stats()
    assert summary["books"] == 2
    assert summary["purchases"] == 1
    assert summary["borrowings"] == 1
    assert summary["returns"] == 1
    books = list_books(q="借用作品", book_type=None, ownership=None, capture_state=None, page=1, page_size=10)
    assert books["items"][0]["authors"] == ["著者A"]


def test_orders_import_skips_semantic_duplicates_from_legacy_db(tmp_path, monkeypatch):
    source = tmp_path / "amazon"
    _write_csvs(source)
    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path / "target"))
    monkeypatch.setattr(config, "AMAZON_DATA_DIR", str(source))
    upgrade_head()
    with with_db() as conn:
        conn.executemany(
            """
            INSERT INTO books(asin,title,title_normalized,category,book_type)
            VALUES (?,?,?,'kindle','unknown')
            """,
            [
                ("B000ORDER1", "旧注文名", "旧注文名"),
                ("B000BORROW", "借用作品", "借用作品"),
            ],
        )
        conn.execute(
            """
            INSERT INTO purchases(order_number,order_date,asin,title,order_status)
            VALUES ('ORDER-1','2026-07-01','B000ORDER1','旧注文名','SUCCESS')
            """
        )
        conn.execute(
            """
            INSERT INTO borrowings(
                asin,title,loan_status,loan_creation_date
            ) VALUES ('B000BORROW','借用作品','ACTIVE','2026-07-02 00:00:00.000000')
            """
        )
        conn.execute(
            """
            INSERT INTO returns(
                asin,title,order_id,return_date
            ) VALUES ('B000ORDER1','旧注文名','ORDER-1','2026-07-03 00:00:00.000000')
            """
        )

    result = run_orders_import()

    assert result["records_processed"] == 0
    summary = stats()
    assert summary["purchases"] == 1
    assert summary["borrowings"] == 1
    assert summary["returns"] == 1
    assert (
        list_books(
            q="旧注文名",
            book_type=None,
            ownership=None,
            capture_state=None,
            page=1,
            page_size=10,
        )["items"][0]["title"]
        == "旧注文名"
    )
