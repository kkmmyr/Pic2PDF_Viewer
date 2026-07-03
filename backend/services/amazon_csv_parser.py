"""Amazon デジタル購入履歴 CSV のパースと書籍マッチング（4.3）。

対象: amazon-order_digital_*.csv
エンコード: UTF-8 with BOM / Shift-JIS 両対応
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass


@dataclass
class ParsedRow:
    csv_title: str
    series_id: str
    volume: int | None
    publisher: str
    authors: list[str]
    asin: str


# ---------------------------------------------------------------------------
# CSV パース
# ---------------------------------------------------------------------------

_PUBLISHER_RE = re.compile(r"\s*\(([^)]+)\)\s*$")
_VOLUME_RE = re.compile(r"(?:第?\s*(\d+)\s*巻|[\s　](\d+)(?:\s*$|\s+(?:\(|（)))")
_ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})/")
_AUTHOR_PREFIX_RE = re.compile(r"^\[Kindle\s*版\]\s*", re.IGNORECASE)
_AUTHOR_SELLER_RE = re.compile(r"\s+販売:.*$")


def _extract_publisher(title: str) -> tuple[str, str]:
    """末尾の "(レーベル名)" を publisher として分離して返す。

    Returns:
        (title_without_publisher, publisher)
    """
    m = _PUBLISHER_RE.search(title)
    if m:
        publisher = m.group(1).strip()
        clean = title[: m.start()].strip()
        return clean, publisher
    return title.strip(), ""


def _extract_volume(title: str) -> tuple[str, int | None]:
    """タイトルから巻番号を抽出して除去する。

    Returns:
        (title_without_volume, volume_int_or_None)
    """
    # 末尾または括弧前の半角数字を巻番号として扱う
    # 例: "おこぼれ姫と円卓の騎士 1" → ("おこぼれ姫と円卓の騎士", 1)
    m = re.search(r"(?:^|[\s　])(\d+)\s*$", title)
    if m:
        vol = int(m.group(1))
        clean = title[: m.start()].strip()
        return clean, vol
    m = _VOLUME_RE.search(title)
    if m:
        vol = int(m.group(1) or m.group(2))
        clean = (title[: m.start()] + title[m.end() :]).strip()
        return clean, vol
    return title.strip(), None


def _parse_authors(fuzetsu: str) -> list[str]:
    """付帯情報フィールドから著者名リストを抽出する。

    例: "[Kindle 版] 石田 リンネ, 起家 一子  販売: Amazon Services..."
    → ["石田 リンネ", "起家 一子"]
    """
    text = _AUTHOR_PREFIX_RE.sub("", fuzetsu)
    text = _AUTHOR_SELLER_RE.sub("", text)
    parts = [p.strip() for p in re.split(r"[,、]", text)]
    return [p for p in parts if p]


def _parse_row(row: dict) -> ParsedRow | None:
    """CSV の 1 行から ParsedRow を生成する。"""
    raw_title = (row.get("商品名") or "").strip()
    if not raw_title:
        return None

    # publisher 抽出
    title_no_pub, publisher = _extract_publisher(raw_title)
    # volume 抽出
    series_id, volume = _extract_volume(title_no_pub)

    # ASIN
    url = row.get("商品URL") or row.get("商品Url") or ""
    asin_m = _ASIN_RE.search(url)
    asin = asin_m.group(1) if asin_m else ""

    # 著者
    fuzetsu = (row.get("付帯情報") or "").strip()
    authors = _parse_authors(fuzetsu) if fuzetsu else []

    return ParsedRow(
        csv_title=raw_title,
        series_id=series_id,
        volume=volume,
        publisher=publisher,
        authors=authors,
        asin=asin,
    )


def _decode(data: bytes) -> str:
    """UTF-8 BOM / Shift-JIS / UTF-8 の順で試みる。"""
    for enc in ("utf-8-sig", "shift_jis", "utf-8"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def parse_csv(file_bytes: bytes) -> list[ParsedRow]:
    """Amazon デジタル購入履歴 CSV バイト列を ParsedRow のリストに変換する。"""
    text = _decode(file_bytes)
    reader = csv.DictReader(io.StringIO(text))
    rows: list[ParsedRow] = []
    for raw in reader:
        parsed = _parse_row(raw)
        if parsed is not None:
            rows.append(parsed)
    return rows
