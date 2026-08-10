"""Amazon デジタル注文・KU借用・返品 CSV の差分取り込み。"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import config
from services._title_normalizer import normalize_title
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.import_run_lifecycle import (
    fail_import_run,
    finish_import_run,
    start_import_run,
)
from utils.dt import jst_now

_FILENAMES = {
    "Digital Content Orders.csv": "purchases",
    "Digital Borrowed Items.csv": "borrowings",
    "Digital Returns.csv": "returns",
}
_REQUIRED_COLUMNS = {
    "purchases": {"ASIN", "Order ID", "Order Date", "Product Name"},
    "borrowings": {"ASIN", "Loan Creation Date", "Loan Status", "Product Name"},
    "returns": {"ASIN", "Return Date", "Product Name"},
}


def _root() -> Path:
    raw = config.AMAZON_DATA_DIR
    if not raw:
        raise ValueError("AMAZON_DATA_DIR が設定されていません")
    root = Path(raw)
    if not root.is_dir():
        raise ValueError("設定された AMAZON_DATA_DIR が見つかりません")
    return root


def _files() -> list[tuple[Path, str]]:
    root = _root().resolve()
    found: list[tuple[Path, str]] = []
    for path in root.rglob("*.csv"):
        resolved = path.resolve()
        if root not in resolved.parents or path.name not in _FILENAMES:
            continue
        found.append((resolved, _FILENAMES[path.name]))
    return sorted(found, key=lambda item: str(item[0]).casefold())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _encoding(path: Path) -> str:
    sample = path.read_bytes()[:65536]
    for encoding in ("utf-8-sig", "cp932", "utf-8"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path.name} の文字コードを判定できません")


def _read_rows(path: Path, kind: str) -> list[dict[str, str]]:
    with path.open("r", encoding=_encoding(path), newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            return []
        reader.fieldnames = [name.lstrip("\ufeff") for name in reader.fieldnames]
        missing = sorted(_REQUIRED_COLUMNS[kind] - set(reader.fieldnames))
        if missing:
            raise ValueError(f"{path.name} の必須カラムが不足しています: {missing}")
        return list(reader)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.casefold() in {"not applicable", "not available"}:
        return None
    return stripped


def _timestamp(value: str | None) -> str | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    normalized = cleaned.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).isoformat()
    except ValueError:
        return cleaned


def _date(value: str | None) -> str:
    cleaned = _clean(value)
    if not cleaned:
        raise ValueError("日付が空です")
    return cleaned[:10]


def _money(value: str | None) -> int | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    number = re.sub(r"[^\d.\-]", "", cleaned)
    if not number:
        return None
    try:
        return int(Decimal(number))
    except InvalidOperation as exc:
        raise ValueError(f"金額を解釈できません: {value}") from exc


def _ensure_book(
    conn,
    *,
    asin: str,
    title: str,
    publisher: str | None = None,
    authors: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO books(asin, title, title_normalized, publisher, category, book_type)
        VALUES (?, ?, ?, ?, 'kindle', 'unknown')
        ON CONFLICT(asin) DO UPDATE SET
            title=excluded.title,
            title_normalized=excluded.title_normalized,
            publisher=COALESCE(excluded.publisher, books.publisher)
        """,
        (asin, title, normalize_title(title), publisher),
    )
    for order, author in enumerate(
        item.strip() for item in (authors or "").replace("、", ",").split(",") if item.strip()
    ):
        key = " ".join(author.casefold().split())
        conn.execute(
            "INSERT INTO authors(name,name_key) VALUES (?,?) ON CONFLICT(name_key) DO UPDATE SET name=excluded.name",
            (author, key),
        )
        author_id = conn.execute("SELECT id FROM authors WHERE name_key=?", (key,)).fetchone()[0]
        conn.execute(
            "INSERT INTO book_authors(asin,author_id,sort_order) VALUES (?,?,?) "
            "ON CONFLICT(asin,author_id) DO UPDATE SET sort_order=excluded.sort_order",
            (asin, author_id, order),
        )


def _import_purchases(conn, rows: list[dict[str, str]], source_file_id: int) -> int:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        asin = (_clean(row.get("ASIN")) or "").upper()
        order_id = _clean(row.get("Order ID")) or ""
        item_id = _clean(row.get("Digital Order Item ID")) or ""
        if asin and order_id:
            groups[(order_id, asin, item_id)].append(row)
    inserted = 0
    for (order_id, asin, item_id), group in groups.items():
        row = group[0]
        if conn.execute(
            "SELECT 1 FROM purchases WHERE order_number=? AND asin=? LIMIT 1",
            (order_id, asin),
        ).fetchone():
            continue
        title = _clean(row.get("Product Name")) or "(タイトル不明)"
        _ensure_book(
            conn,
            asin=asin,
            title=title,
            publisher=_clean(row.get("Publisher")) or _clean(row.get("Seller of Record")),
        )
        before = conn.total_changes
        conn.execute(
            """
            INSERT INTO purchases(
                order_number, order_date, asin, title, price, order_status,
                digital_order_item_id, source_file_id, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(order_number,asin,title) DO NOTHING
            """,
            (
                order_id,
                _date(row.get("Order Date")),
                asin,
                title,
                _money(row.get("Price")),
                _clean(row.get("Order Status")) or "SUCCESS",
                item_id or None,
                source_file_id,
                jst_now().isoformat(),
            ),
        )
        inserted += int(conn.total_changes > before)
    return inserted


def _import_borrowings(conn, rows: list[dict[str, str]], source_file_id: int) -> int:
    inserted = 0
    for row in rows:
        asin = (_clean(row.get("ASIN")) or "").upper()
        creation = _timestamp(row.get("Loan Creation Date"))
        if not asin or not creation:
            continue
        if conn.execute(
            """
            SELECT 1 FROM borrowings
            WHERE asin=? AND datetime(loan_creation_date)=datetime(?)
            LIMIT 1
            """,
            (asin, creation),
        ).fetchone():
            continue
        title = _clean(row.get("Product Name")) or "(タイトル不明)"
        authors = _clean(row.get("Author"))
        _ensure_book(conn, asin=asin, title=title, authors=authors)
        before = conn.total_changes
        conn.execute(
            """
            INSERT INTO borrowings(
                asin,title,authors,loan_program,loan_status,loan_creation_date,
                loan_acceptance_date,end_date,source_file_id,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(asin,loan_creation_date) DO NOTHING
            """,
            (
                asin,
                title,
                authors,
                _clean(row.get("Loan Program")),
                _clean(row.get("Loan Status")) or "UNKNOWN",
                creation,
                _timestamp(row.get("Loan Acceptance Date")),
                _timestamp(row.get("End Date")),
                source_file_id,
                jst_now().isoformat(),
            ),
        )
        inserted += int(conn.total_changes > before)
    return inserted


def _import_returns(conn, rows: list[dict[str, str]], source_file_id: int) -> int:
    inserted = 0
    seen: set[tuple[str, str | None, str]] = set()
    for row in rows:
        success = (_clean(row.get("Processing Successful")) or "Yes").casefold()
        if success != "yes":
            continue
        asin = (_clean(row.get("ASIN")) or "").upper()
        returned_at = _timestamp(row.get("Return Date"))
        order_id = _clean(row.get("Order ID"))
        key = (asin, order_id, returned_at or "")
        if not asin or not returned_at or key in seen:
            continue
        seen.add(key)
        if conn.execute(
            """
            SELECT 1 FROM returns
            WHERE asin=? AND order_id IS ? AND datetime(return_date)=datetime(?)
            LIMIT 1
            """,
            (asin, order_id, returned_at),
        ).fetchone():
            continue
        title = _clean(row.get("Product Name")) or "(タイトル不明)"
        _ensure_book(conn, asin=asin, title=title)
        before = conn.total_changes
        conn.execute(
            """
            INSERT INTO returns(
                asin,title,order_id,refund_amount,return_date,return_status,
                source_file_id,created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(asin,order_id,return_date) DO NOTHING
            """,
            (
                asin,
                title,
                order_id,
                _money(row.get("Amount Refunded")),
                returned_at,
                _clean(row.get("Return Status")),
                source_file_id,
                jst_now().isoformat(),
            ),
        )
        inserted += int(conn.total_changes > before)
    return inserted


def run_orders_import() -> dict:
    """設定済みルートの対応 CSV を SHA-256 差分で取り込む。"""
    files = _files()
    run_id = start_import_run("amazon_orders")

    processed_files = 0
    skipped_files = 0
    records = 0
    results: list[dict] = []
    try:
        for path, kind in files:
            digest = _sha256(path)
            with with_db() as conn:
                if conn.execute(
                    "SELECT 1 FROM imported_files WHERE source_kind=? AND filename=? AND sha256=?",
                    (kind, path.name, digest),
                ).fetchone():
                    skipped_files += 1
                    results.append({"filename": path.name, "kind": kind, "status": "skipped", "records": 0})
                    continue
                rows = _read_rows(path, kind)
                source_file_id = conn.execute(
                    """
                    INSERT INTO imported_files(
                        source_kind,filename,sha256,imported_at,record_count,status
                    ) VALUES (?,?,?,?,0,'running')
                    """,
                    (kind, path.name, digest, jst_now().isoformat()),
                ).lastrowid
                handlers = {
                    "purchases": _import_purchases,
                    "borrowings": _import_borrowings,
                    "returns": _import_returns,
                }
                count = handlers[kind](conn, rows, source_file_id)
                conn.execute(
                    "UPDATE imported_files SET record_count=?, status='success' WHERE id=?",
                    (count, source_file_id),
                )
                processed_files += 1
                records += count
                results.append({"filename": path.name, "kind": kind, "status": "success", "records": count})
    except Exception as exc:
        fail_import_run(run_id, exc)
        raise

    finish_import_run(
        run_id,
        status="succeeded",
        files=processed_files,
        records=records,
        skipped=skipped_files,
    )
    return {
        "run_id": run_id,
        "status": "succeeded",
        "files_processed": processed_files,
        "files_skipped": skipped_files,
        "records_processed": records,
        "files": results,
    }
