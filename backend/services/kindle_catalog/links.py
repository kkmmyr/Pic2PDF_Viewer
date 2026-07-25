"""Pic2PDFViewer 既存画像と Kindle ASIN の手動紐付け。"""

from __future__ import annotations

import os
from pathlib import Path

from config import get_dirs_by_source
from services._title_normalizer import normalize_title
from services.kindle_catalog.connection import with_db
from services.meta_store import load_meta, update_meta_locked
from utils.file_utils import is_image_file
from utils.path_utils import resolve_under_base, validate_safe_path

_LINKABLE_SOURCES = ("comic", "novel")


def _validate_source(source: str) -> None:
    if source not in _LINKABLE_SOURCES:
        raise ValueError("紐付け対象 source は comic または novel です")


def _book_dir(source: str, book_id: str) -> Path:
    _validate_source(source)
    validate_safe_path(book_id, param_name="book_id")
    if not book_id.lower().endswith(".pdf"):
        raise ValueError("book_id は .pdf で終わる必要があります")
    relative = book_id[:-4]
    target = Path(resolve_under_base(get_dirs_by_source(source)["img"], relative))
    if not target.is_dir() or not any(is_image_file(item.name) for item in target.iterdir() if item.is_file()):
        raise ValueError("Pic2PDFViewer の画像書籍が見つかりません")
    return target


def _image_books(source: str) -> list[str]:
    _validate_source(source)
    base = Path(get_dirs_by_source(source)["img"])
    if not base.is_dir():
        return []
    result: list[str] = []
    for root, _dirs, files in os.walk(base):
        if not any(is_image_file(filename) for filename in files):
            continue
        relative = Path(root).relative_to(base).as_posix()
        if relative != ".":
            result.append(f"{relative}.pdf")
    return sorted(result, key=str.casefold)


def list_unlinked() -> list[dict]:
    """Pic2PDFViewer 内に実在し、ASIN 未設定の comic/novel を返す。"""
    items: list[dict] = []
    for source in _LINKABLE_SOURCES:
        meta = load_meta(source)
        for book_id in _image_books(source):
            entry = meta.get(book_id, {})
            if entry.get("asin"):
                continue
            items.append(
                {
                    "source": source,
                    "book_id": book_id,
                    "title": Path(book_id).stem,
                    "authors": entry.get("authors", []),
                    "series_title": entry.get("series_title"),
                }
            )
    return items


def candidates(source: str, book_id: str, limit: int = 10) -> list[dict]:
    """タイトル等による候補を返す。確定更新は行わない。"""
    _book_dir(source, book_id)
    meta = load_meta(source).get(book_id, {})
    title = Path(book_id).stem
    normalized = normalize_title(title).casefold()
    expected_type = "comic" if source == "comic" else "novel"
    expected_authors = {author.casefold() for author in meta.get("authors", [])}
    with with_db() as conn:
        rows = conn.execute(
            """
            SELECT b.asin, b.title, b.title_normalized, b.book_type,
                   (SELECT GROUP_CONCAT(name, ' / ') FROM (
                       SELECT a.name AS name
                       FROM book_authors ba JOIN authors a ON a.id=ba.author_id
                       WHERE ba.asin=b.asin ORDER BY ba.sort_order
                   )) AS authors
            FROM books b
            """
        ).fetchall()

    ranked: list[dict] = []
    for row in rows:
        candidate_normalized = (row["title_normalized"] or normalize_title(row["title"])).casefold()
        score = 0
        reasons: list[str] = []
        if candidate_normalized == normalized:
            score += 100
            reasons.append("正規化タイトル一致")
        elif normalized and (normalized in candidate_normalized or candidate_normalized in normalized):
            score += 45
            reasons.append("タイトル部分一致")
        if row["book_type"] == expected_type:
            score += 15
            reasons.append("書籍種別一致")
        candidate_authors = {author.casefold() for author in (row["authors"] or "").split(" / ") if author}
        common_authors = expected_authors & candidate_authors
        if common_authors:
            score += 20 * len(common_authors)
            reasons.append("著者一致")
        if score <= 15:
            continue
        ranked.append(
            {
                "asin": row["asin"],
                "title": row["title"],
                "authors": row["authors"].split(" / ") if row["authors"] else [],
                "book_type": row["book_type"],
                "score": score,
                "reasons": reasons,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["title"]))
    return ranked[:limit]


def link(source: str, book_id: str, asin: str) -> dict:
    """確認済み ASIN だけを既存メタデータへ追加する。"""
    _book_dir(source, book_id)
    with with_db() as conn:
        if conn.execute("SELECT 1 FROM books WHERE asin=?", (asin,)).fetchone() is None:
            raise ValueError("指定 ASIN は Kindle カタログに存在しません")

    def _apply(data):
        entry = data.setdefault(book_id, {"authors": []})
        entry["asin"] = asin

    update_meta_locked(source, _apply)
    return {"source": source, "book_id": book_id, "asin": asin}


def unlink(source: str, book_id: str) -> dict:
    """ASIN だけを解除し、他のメタデータを保持する。"""
    _book_dir(source, book_id)

    def _apply(data):
        if book_id in data:
            data[book_id].pop("asin", None)

    update_meta_locked(source, _apply)
    return {"source": source, "book_id": book_id, "unlinked": True}
