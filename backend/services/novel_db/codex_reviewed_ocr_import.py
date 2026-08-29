"""Fail-closed staging import for sealed Codex-reviewed OCR packages."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from utils.path_utils import resolve_under_base

from .codex_reviewed_ocr import IMPORTED_ENGINE, _canonical_json, validate_reviewed_package
from .connection import open_db


def _input_images(images_root: Path, book_name: str) -> list[tuple[int, Path, str]]:
    book_dir = Path(resolve_under_base(images_root, book_name, param_name="book_name"))
    if not book_dir.is_dir():
        raise FileNotFoundError(f"images dir not found: {book_dir}")
    numbered = sorted(
        ((int(path.stem), path) for path in book_dir.glob("*.png") if path.stem.isdigit()),
        key=lambda item: item[0],
    )
    expected = list(range(1, len(numbered) + 1))
    if not numbered or [page_no for page_no, _ in numbered] != expected:
        raise ValueError("production PNG page numbers must be contiguous from 1")
    result: list[tuple[int, Path, str]] = []
    for page_no, path in numbered:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        result.append((page_no, path, digest))
    return result


def _verify_production_images(package: dict[str, Any], images_root: Path) -> None:
    images = _input_images(images_root, str(package["book_name"]))
    if len(images) != package["source_page_count"]:
        raise ValueError("production image page count mismatch")
    for page, (page_no, _path, digest) in zip(package["pages"], images, strict=True):
        if page["page_no"] != page_no or page["image_sha256"] != digest:
            raise ValueError(f"production image SHA-256 mismatch: page {page_no}")


def _existing_run_matches(conn: sqlite3.Connection, run_id: int, package: dict[str, Any]) -> bool:
    rows = conn.execute(
        "SELECT page_no, image_sha256, full_text, raw_output, quality_flags_json, qa_state, qa_note, "
        "page_type, index_eligible, layout_type, primary_text, external_text, selected_engine, corrected_text, "
        "selection_reason FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
        (run_id,),
    ).fetchall()
    if len(rows) != len(package["pages"]):
        return False
    for row, page in zip(rows, package["pages"], strict=True):
        if (
            int(row[0]) != page["page_no"]
            or str(row[1]) != page["image_sha256"]
            or str(row[2] or "") != page["full_text"]
            or str(row[3] or "") != page["raw_output"]
            or json.loads(str(row[4])) != page["quality_flags"]
            or str(row[5]) != page["qa_state"]
            or str(row[6] or "") != str(page["qa_note"] or "")
            or str(row[7]) != page["page_type"]
            or bool(row[8]) != page["index_eligible"]
            or str(row[9]) != page["layout_type"]
            or row[10] != page["primary_text"]
            or row[11] != page["external_text"]
            or str(row[12]) != page["selected_engine"]
            or row[13] != page["corrected_text"]
            or row[14] != page["selection_reason"]
        ):
            return False
    return True


def import_reviewed_package(
    *,
    db_path: Path,
    images_root: Path,
    package: dict[str, Any],
) -> dict[str, Any]:
    package = validate_reviewed_package(package)
    _verify_production_images(package, images_root)
    digest = str(package["package_sha256"])
    imported_model = f"{package['model']}/codex-reviewed:{digest}"
    with open_db(str(db_path)) as conn:
        existing = conn.execute(
            "SELECT id FROM ocr_runs WHERE book_name=? AND engine=? AND model=? "
            "AND source_page_count=? ORDER BY id DESC LIMIT 1",
            (package["book_name"], IMPORTED_ENGINE, imported_model, package["source_page_count"]),
        ).fetchone()
        if existing is not None:
            run_id = int(existing[0])
            if not _existing_run_matches(conn, run_id, package):
                raise ValueError("existing reviewed OCR import conflicts with package")
            return {
                "run_id": run_id,
                "inserted": 0,
                "idempotent": len(package["pages"]),
                "package_sha256": digest,
            }
        conflicting = conn.execute(
            "SELECT id FROM ocr_runs WHERE book_name=? AND engine=? AND state='awaiting_qa' LIMIT 1",
            (package["book_name"], IMPORTED_ENGINE),
        ).fetchone()
        if conflicting is not None:
            raise ValueError("another reviewed OCR package is already awaiting publication")
        with conn:
            cursor = conn.execute(
                "INSERT INTO ocr_runs "
                "(book_name, engine, model, source_page_count, state, started_at, qa_state, qa_note) "
                "VALUES (?, ?, ?, ?, 'awaiting_qa', datetime('now', '+9 hours'), 'pending', ?)",
                (
                    package["book_name"],
                    IMPORTED_ENGINE,
                    imported_model,
                    package["source_page_count"],
                    f"Codex-reviewed package {digest}; actor={package['review']['actor']}; "
                    f"note={package['review']['note']}",
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("failed to create reviewed OCR import run")
            run_id = int(cursor.lastrowid)
            for page in package["pages"]:
                conn.execute(
                    "INSERT INTO ocr_page_results "
                    "(run_id, page_no, image_sha256, state, full_text, char_count, raw_output, block_count, "
                    "quality_flags_json, ink_coverage, attempt_count, error_message, qa_state, qa_note, reviewed_at, "
                    "page_type, index_eligible, layout_type, primary_text, external_text, selected_engine, "
                    "corrected_text, published_text, selection_reason, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, "
                    "datetime('now', '+9 hours'))",
                    (
                        run_id,
                        page["page_no"],
                        page["image_sha256"],
                        page["state"],
                        page["full_text"],
                        page["char_count"],
                        page["raw_output"],
                        page["block_count"],
                        _canonical_json(page["quality_flags"]),
                        page["ink_coverage"],
                        page["attempt_count"],
                        page["error_message"],
                        page["qa_state"],
                        page["qa_note"],
                        page["reviewed_at"],
                        page["page_type"],
                        page["index_eligible"],
                        page["layout_type"],
                        page["primary_text"],
                        page["external_text"],
                        page["selected_engine"],
                        page["corrected_text"],
                        page["selection_reason"],
                    ),
                )
    return {
        "run_id": run_id,
        "inserted": len(package["pages"]),
        "idempotent": 0,
        "package_sha256": digest,
    }
