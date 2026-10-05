"""Version-pinned publication of independently reviewed GPT-6.1 OCR bodies."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from utils.path_utils import validate_safe_name

from .connection import with_db
from .ocr_publication_backup import create_verified_publication_backup
from .ocr_publication_history import PublicationPage, ensure_legacy_snapshot, publish_pages
from .ocr_run_store import OcrInputPage
from .page_fts_state import mark_page_fts_stale

SCHEMA = "gpt61-body-publication-v1"
ENGINE = "gpt61_body_reviewed_v1"
MODEL = "gpt-6.1-sol"
_BODY_TYPES = {"narrative", "afterword"}
_TYPE_MAP = {
    "narrative": "narrative",
    "afterword": "narrative",
    "toc": "toc",
    "cover": "illustration",
    "title": "illustration",
    "illustration": "illustration",
    "blank": "illustration",
    "other": "illustration",
    "rights": "colophon_or_ad",
    "advertisement": "colophon_or_ad",
    "colophon": "colophon_or_ad",
}


def digest_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def package_digest(package: dict[str, Any]) -> str:
    return digest_json({key: value for key, value in package.items() if key != "package_sha256"})


def _sha(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid SHA256")
    return value


def validate_package(package: dict[str, Any]) -> None:
    expected = {
        "schema",
        "package_sha256",
        "book_name",
        "model",
        "source_artifact",
        "quality",
        "expected_current_sha256",
        "pages",
    }
    if set(package) != expected or package["schema"] != SCHEMA or package["model"] != MODEL:
        raise ValueError("unsupported GPT-6.1 publication contract")
    validate_safe_name(package["book_name"], param_name="book_name")
    if package_digest(package) != _sha(package["package_sha256"]):
        raise ValueError("package digest mismatch")
    _sha(package["expected_current_sha256"])
    source = package["source_artifact"]
    if not isinstance(source, dict) or not source.get("schema") or not source.get("path"):
        raise ValueError("source artifact provenance required")
    _sha(source.get("sha256"))
    _validate_quality(package["quality"])
    pages = package["pages"]
    if not isinstance(pages, list) or not pages:
        raise ValueError("empty pages")
    for number, page in enumerate(pages, 1):
        _validate_page(page, number)


def _validate_quality(quality: Any) -> None:
    if (
        not isinstance(quality, dict)
        or quality.get("verdict") != "accepted"
        or quality.get("unresolved_body") != 0
        or quality.get("unresolved_findings") != 0
    ):
        raise ValueError("quality hold or missing acceptance")
    evidence = quality.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("quality evidence required")
    for item in evidence:
        if not isinstance(item, dict) or not item.get("path"):
            raise ValueError("invalid quality evidence")
        _sha(item.get("sha256"))


def publication_text(page: dict[str, Any]) -> str:
    """Resolve only the explicitly sealed source field, never a heuristic fallback."""
    field = page.get("body_text_field", "text")
    if field not in {"text", "other_text"}:
        raise ValueError("invalid body text field")
    if field == "other_text":
        if page.get("page_type") != "afterword" or page.get("text") != "":
            raise ValueError("other_text adoption requires an empty-text afterword")
        value = page.get("artifact", {}).get("other_text")
        if not isinstance(value, str):
            raise ValueError("reviewed afterword other_text is required")
        return value
    return page["text"]


def _validate_page(page: dict[str, Any], number: int) -> None:
    if type(page.get("page_no")) is not int or page["page_no"] != number:
        raise ValueError("pages must be contiguous")
    if page.get("page_type") not in _TYPE_MAP or not isinstance(page.get("text"), str):
        raise ValueError("invalid page classification or text")
    _sha(page.get("image_sha256"))
    _sha(page.get("final_sha256"))
    if page["page_type"] in _BODY_TYPES:
        if not publication_text(page).strip() or page.get("uncertain_spans"):
            raise ValueError("empty or unresolved body page")
    if not isinstance(page.get("artifact"), dict):
        raise ValueError("original page artifact required")
    original = page["artifact"]
    if any(original.get(key) != page[key] for key in ("page_no", "page_type", "text", "image_sha256")):
        raise ValueError("final artifact differs from publication page")
    if original.get("model") != MODEL:
        raise ValueError("final artifact model mismatch")


def current_digest(conn: sqlite3.Connection, book_name: str) -> str:
    book = conn.execute("SELECT id FROM books WHERE name=?", (book_name,)).fetchone()
    if book is None:
        return digest_json({"book": book_name, "pages": [], "active_run": None})
    rows = conn.execute(
        "SELECT page_no, image_path, full_text, page_type, index_eligible FROM pages WHERE book_id=? ORDER BY page_no",
        (book[0],),
    ).fetchall()
    active = conn.execute(
        "SELECT run_id FROM ocr_publications WHERE book_id=? AND retired_at IS NULL", (book[0],)
    ).fetchone()
    return digest_json(
        {"book": book_name, "pages": [list(row) for row in rows], "active_run": active[0] if active else None}
    )


def _load_images(images_root: Path, package: dict[str, Any]) -> list[OcrInputPage]:
    root = images_root.resolve(strict=True)
    directory = (root / package["book_name"]).resolve(strict=True)
    if not directory.is_relative_to(root):
        raise ValueError("source path escaped images root")
    numbered = sorted((int(p.stem), p) for p in directory.glob("*.png") if p.stem.isdigit())
    if [number for number, _ in numbered] != list(range(1, len(package["pages"]) + 1)):
        raise ValueError("source page count changed")
    inputs = []
    for (number, path), page in zip(numbered, package["pages"], strict=True):
        with path.open("rb") as handle:
            sha = hashlib.file_digest(handle, "sha256").hexdigest()
        if sha != page["image_sha256"]:
            raise ValueError(f"source image changed: page {number}")
        inputs.append(OcrInputPage(number, path, sha))
    return inputs


def _verify_published(conn: sqlite3.Connection, package: dict[str, Any], run_id: int) -> dict[str, Any]:
    name = package["book_name"]
    book = conn.execute("SELECT id, ocr_done_at, indexed_at FROM books WHERE name=?", (name,)).fetchone()
    active = (
        conn.execute(
            "SELECT run_id, note FROM ocr_publications WHERE book_id=? AND retired_at IS NULL", (book[0],)
        ).fetchone()
        if book
        else None
    )
    if not active or active[0] != run_id:
        raise ValueError("same artifact is no longer the active publication")
    rows = conn.execute(
        "SELECT page_no, full_text, page_type, index_eligible FROM pages WHERE book_id=? ORDER BY page_no", (book[0],)
    ).fetchall()
    expected = [
        [
            p["page_no"],
            publication_text(p) if p["page_type"] in _BODY_TYPES else "",
            _TYPE_MAP[p["page_type"]],
            p["page_type"] in _BODY_TYPES,
        ]
        for p in package["pages"]
    ]
    if [list(row) for row in rows] != expected:
        raise ValueError("published body differs from sealed artifact")
    conn.execute("INSERT INTO pages_fts(pages_fts, rank) VALUES('integrity-check', 1)")
    return {
        "book_name": name,
        "run_id": run_id,
        "package_sha256": package["package_sha256"],
        "body_published": bool(book[1]),
        "rag_available": book[2] is not None,
        "pages_verified": len(rows),
        "body_characters": sum(len(row[1]) for row in expected),
        "fts5_integrity": "ok",
        "publication_note": active[1],
        "current_sha256": current_digest(conn, name),
    }


def publish_package(*, db_path: Path, images_root: Path, package: dict[str, Any]) -> dict[str, Any]:
    validate_package(package)
    inputs = _load_images(images_root, package)
    name = package["book_name"]
    with with_db(str(db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute(
            "SELECT id FROM ocr_runs WHERE book_name=? AND engine=? AND json_extract(runtime_manifest_json, '$.package_sha256')=?",
            (name, ENGINE, package["package_sha256"]),
        ).fetchall()
        if prior:
            if len(prior) != 1:
                raise ValueError("duplicate imported artifact identity")
            return {**_verify_published(conn, package, int(prior[0][0])), "status": "already_published"}
        if current_digest(conn, name) != package["expected_current_sha256"]:
            raise ValueError("current publication changed; refusing version overwrite")
        provenance = {
            "schema": SCHEMA,
            "model": MODEL,
            "package_sha256": package["package_sha256"],
            "source_artifact": package["source_artifact"],
            "quality": package["quality"],
        }
        cursor = conn.execute(
            "INSERT INTO ocr_runs (book_name, engine, model, source_page_count, state, started_at, qa_state, runtime_manifest_json) VALUES (?, ?, ?, ?, 'awaiting_qa', datetime('now', '+9 hours'), 'pending', ?)",
            (name, ENGINE, MODEL, len(inputs), json.dumps(provenance, ensure_ascii=False)),
        )
        run_id = int(cursor.lastrowid)
        backup = create_verified_publication_backup(run_id, "publish", db_path=db_path)
        note = f"GPT-6.1 quality accepted; package={package['package_sha256']}; verified backup={backup}"
        book = conn.execute("SELECT id FROM books WHERE name=?", (name,)).fetchone()
        if book is None:
            cursor = conn.execute(
                "INSERT INTO books (name, pdf_path, images_dir, page_count, ocr_done_at) VALUES (?, '', ?, ?, datetime('now', '+9 hours'))",
                (name, str(inputs[0].image_path.parent), len(inputs)),
            )
            book_id = int(cursor.lastrowid)
        else:
            book_id = int(book[0])
            ensure_legacy_snapshot(conn, book_id=book_id, book_name=name, input_pages=inputs, actor="codex")
        conn.execute(
            "UPDATE books SET images_dir=?, page_count=?, indexed_at=NULL, ocr_done_at=datetime('now', '+9 hours') WHERE id=?",
            (str(inputs[0].image_path.parent), len(inputs), book_id),
        )
        publications = []
        for page, image in zip(package["pages"], inputs, strict=True):
            body = page["page_type"] in _BODY_TYPES
            text = publication_text(page) if body else ""
            kind = _TYPE_MAP[page["page_type"]]
            conn.execute(
                "INSERT INTO ocr_page_results (run_id, page_no, image_sha256, state, full_text, primary_text, char_count, raw_output, qa_state, qa_note, reviewed_at, page_type, layout_type, selected_engine, index_eligible) VALUES (?, ?, ?, 'passed', ?, ?, ?, ?, 'approved', ?, datetime('now', '+9 hours'), ?, ?, 'primary', ?)",
                (
                    run_id,
                    page["page_no"],
                    image.image_sha256,
                    publication_text(page),
                    publication_text(page),
                    len(publication_text(page)),
                    json.dumps(page, ensure_ascii=False),
                    note,
                    kind,
                    "normal_prose" if body else "structured",
                    body,
                ),
            )
            publications.append(
                PublicationPage(image.page_no, str(image.image_path), image.image_sha256, text, kind, body)
            )
        publish_pages(
            conn, book_id=book_id, run_id=run_id, pages=publications, actor="codex", action="publish", note=note
        )
        mark_page_fts_stale(conn)
        conn.execute(
            "UPDATE ocr_runs SET state='completed', qa_state='approved', qa_reviewer='codex', qa_reviewed_at=datetime('now', '+9 hours'), finished_at=datetime('now', '+9 hours'), qa_note=? WHERE id=?",
            (note, run_id),
        )
        result = _verify_published(conn, package, run_id)
        return {**result, "status": "published", "backup": backup}
