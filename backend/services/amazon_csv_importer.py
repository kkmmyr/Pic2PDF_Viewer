"""Amazon 購入履歴 CSV から novel/comic ライブラリの authors/asin を補完する。

固定パスから 2 種類の CSV を読み込んで統合し、既存 meta.json エントリを
空欄のときのみ補完する（既存値は上書きしない）。

CSV ソース:
  1. Digital Content Orders.csv  — 全期間エクスポート（ASIN + タイトル、著者なし）
  2. amazon-order_digital/*.csv  — 月別デジタル注文（著者情報あり、2021 年〜）
"""

from __future__ import annotations

import csv
import io
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from config import AMAZON_DATA_DIR
from services._title_normalizer import is_meaningful as _is_meaningful
from services._title_normalizer import normalize_title
from services.amazon_csv_parser import ParsedRow
from services.amazon_csv_parser import parse_csv as _parse_monthly_bytes
from services.meta_store import update_meta_locked

# タイトル正規化は _title_normalizer に移管。テスト後方互換エイリアス。
_normalize = normalize_title

# ---------------------------------------------------------------------------
# 固定パス
# ---------------------------------------------------------------------------
_ROOT = Path(AMAZON_DATA_DIR) if AMAZON_DATA_DIR else None
_DIGITAL_ORDERS_PATH = _ROOT / "amazon-order" / "Your Amazon Orders" / "Digital Content Orders.csv" if _ROOT else None
_MONTHLY_CSV_DIR = _ROOT / "amazon-order_digital" if _ROOT else None

# ---------------------------------------------------------------------------
# サブスク / 音楽除外
# ---------------------------------------------------------------------------
_SUBSCRIPTION_ASINS = {"B0733PCPRF", "B075JQ5JR5", "B00NVK0UZQ"}
_SUBSCRIPTION_TYPES = {"Subscription_Renewal", "Subscription_Signup"}
_MUSIC_SELLERS = {"amazon.com sales, inc."}


# ---------------------------------------------------------------------------
# データ型
# ---------------------------------------------------------------------------
@dataclass
class _LookupEntry:
    asin: str
    title: str
    authors: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    updated: int = 0
    skipped: int = 0
    unmatched: int = 0


# ---------------------------------------------------------------------------
# CSV 読み込み
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    """BOM / SJIS / UTF-8 を順に試みてテキストを返す。"""
    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_digital_orders(path: Path) -> dict[str, _LookupEntry]:
    """Digital Content Orders.csv → {asin: _LookupEntry}。

    - (Order ID, ASIN, Digital Order Item ID) 単位で重複行を集約
    - サブスク / 音楽 は除外
    """
    if not path.exists():
        return {}

    text = _read_text(path)
    # BOM が残る場合に備えてヘッダー行の先頭をクリーン
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return {}
    reader.fieldnames = [h.lstrip("﻿") for h in reader.fieldnames]

    for row in reader:
        order_id = (row.get("Order ID") or "").strip()
        asin = (row.get("ASIN") or "").strip()
        doi_id = (row.get("Digital Order Item ID") or "").strip()
        if not asin or not order_id:
            continue
        groups[(order_id, asin, doi_id)].append(row)

    result: dict[str, _LookupEntry] = {}
    for (_order_id, asin, _doi), rows in groups.items():
        if asin in result:
            continue
        if asin in _SUBSCRIPTION_ASINS:
            continue
        base = rows[0]
        sub_type = (base.get("Subscription Order Type") or "").strip()
        if sub_type in _SUBSCRIPTION_TYPES:
            continue
        seller = (base.get("Seller of Record") or "").strip().lower()
        if seller in _MUSIC_SELLERS:
            continue
        title = (base.get("Product Name") or "").strip()
        if not _is_meaningful(title):
            continue
        result[asin] = _LookupEntry(asin=asin, title=title)

    return result


def _parse_monthly(csv_dir: Path) -> list[ParsedRow]:
    """amazon-order_digital/*.csv から全 ParsedRow を返す。"""
    if not csv_dir.exists():
        return []
    rows: list[ParsedRow] = []
    for f in sorted(csv_dir.glob("*.csv")):
        rows.extend(_parse_monthly_bytes(f.read_bytes()))
    return rows


def _build_lookup(
    digital: dict[str, _LookupEntry],
    monthly: list[ParsedRow],
) -> dict[str, _LookupEntry]:
    """2 ソースを ASIN で統合した lookup テーブルを返す。"""
    table = dict(digital)

    # 月別 CSV でエントリ追加 / 著者補完
    seen: set[str] = set()
    for row in monthly:
        if not row.asin:
            continue
        if row.asin in seen:
            continue
        seen.add(row.asin)
        if row.asin in table:
            if not table[row.asin].authors and row.authors:
                table[row.asin].authors = row.authors
        else:
            table[row.asin] = _LookupEntry(
                asin=row.asin,
                title=row.csv_title,
                authors=row.authors,
            )

    return table


# ---------------------------------------------------------------------------
# マッチング
# ---------------------------------------------------------------------------


def _build_norm_index(
    lookup: dict[str, _LookupEntry],
) -> list[tuple[str, _LookupEntry]]:
    """(正規化タイトル小文字, entry) のリストを返す（タイトルマッチ用）。"""
    result = []
    for entry in lookup.values():
        norm = _normalize(entry.title).lower()
        if len(norm) >= 3:
            result.append((norm, entry))
    return result


def _match(
    key: str,
    existing: dict,
    lookup: dict[str, _LookupEntry],
    norm_index: list[tuple[str, _LookupEntry]],
) -> _LookupEntry | None:
    """meta.json のキーに対応する lookup エントリを返す。"""
    # 1. エントリに ASIN があれば直接引く
    existing_asin = (existing.get("asin") or "").strip()
    if existing_asin and existing_asin in lookup:
        return lookup[existing_asin]

    # 2. ファイル名ステムで包含チェック
    stem = Path(Path(key).name).stem  # "path/book.pdf" → "book"
    stem_norm = unicodedata.normalize("NFKC", stem).lower()
    for norm_title, entry in norm_index:
        if norm_title in stem_norm:
            return entry

    return None


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------


def run_import(source: str) -> ImportResult:
    """固定パスの CSV を読み込んで meta.json を著者/ASIN で補完する。

    Args:
        source: 'novel' | 'comic'

    Returns:
        ImportResult(updated, skipped, unmatched)

    Raises:
        ValueError: CSV が 1 件も見つからない場合
    """
    if _DIGITAL_ORDERS_PATH is None or _MONTHLY_CSV_DIR is None:
        raise ValueError("AMAZON_DATA_DIR が設定されていません。.env で AMAZON_DATA_DIR を指定してください。")

    digital = _parse_digital_orders(_DIGITAL_ORDERS_PATH)
    monthly = _parse_monthly(_MONTHLY_CSV_DIR)

    if not digital and not monthly:
        raise ValueError(
            f"Amazon CSV が見つかりません。パスを確認してください: {_DIGITAL_ORDERS_PATH.parent} / {_MONTHLY_CSV_DIR}"
        )

    lookup = _build_lookup(digital, monthly)
    norm_index = _build_norm_index(lookup)

    result = ImportResult()

    def _updater(meta: dict) -> None:
        for key, existing in meta.items():
            entry = _match(key, existing, lookup, norm_index)
            if entry is None:
                result.unmatched += 1
                continue

            needs_authors = not existing.get("authors") and bool(entry.authors)
            needs_asin = not existing.get("asin") and bool(entry.asin)

            if needs_authors or needs_asin:
                new_entry = dict(existing)
                if needs_authors:
                    new_entry["authors"] = entry.authors
                if needs_asin:
                    new_entry["asin"] = entry.asin
                meta[key] = new_entry
                result.updated += 1
            else:
                result.skipped += 1

    update_meta_locked(source, _updater)
    return result
