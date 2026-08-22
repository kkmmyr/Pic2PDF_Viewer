"""Versioned OCR publication and exact canonical rollback."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .connection import open_db, with_db
from .ocr_run_store import OcrInputPage, collect_input_pages


@dataclass(frozen=True)
class PublicationPage:
    page_no: int
    image_path: str
    image_sha256: str
    published_text: str
    page_type: str
    index_eligible: bool


def _active_publication_id(conn: sqlite3.Connection, book_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM ocr_publications WHERE book_id=? AND retired_at IS NULL",
        (book_id,),
    ).fetchone()
    return None if row is None else int(row[0])


def ensure_legacy_snapshot(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    book_name: str,
    input_pages: list[OcrInputPage],
    actor: str,
) -> int | None:
    """Snapshot current canonical pages once before their first versioned replacement."""
    active_id = _active_publication_id(conn, book_id)
    if active_id is not None:
        row = conn.execute("SELECT run_id FROM ocr_publications WHERE id=?", (active_id,)).fetchone()
        return None if row is None else int(row[0])

    canonical_rows = conn.execute(
        "SELECT page_no, full_text, page_type, index_eligible "
        "FROM pages WHERE book_id=? AND page_no BETWEEN 1 AND ? ORDER BY page_no",
        (book_id, len(input_pages)),
    ).fetchall()
    if not canonical_rows:
        return None
    expected_page_numbers = [page.page_no for page in input_pages]
    actual_page_numbers = [int(row[0]) for row in canonical_rows]
    if actual_page_numbers != expected_page_numbers:
        raise ValueError(
            f"canonical pages are incomplete for legacy snapshot: {len(actual_page_numbers)}/{len(input_pages)}"
        )

    cursor = conn.execute(
        "INSERT INTO ocr_runs "
        "(book_name, engine, model, source_page_count, state, started_at, finished_at, "
        "qa_state, qa_reviewer, qa_reviewed_at, qa_note) "
        "VALUES (?, 'legacy', 'pre-sol-snapshot', ?, 'completed', "
        "datetime('now', '+9 hours'), datetime('now', '+9 hours'), 'approved', ?, "
        "datetime('now', '+9 hours'), 'canonical pages snapshot before versioned OCR publication')",
        (book_name, len(input_pages), actor),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("failed to create legacy OCR run")
    legacy_run_id = int(cursor.lastrowid)

    input_by_page = {page.page_no: page for page in input_pages}
    for row in canonical_rows:
        page_no = int(row[0])
        published_text = str(row[1] or "")
        page_type = str(row[2] or "narrative")
        index_eligible = bool(row[3])
        input_page = input_by_page[page_no]
        conn.execute(
            "INSERT INTO ocr_page_results "
            "(run_id, page_no, image_sha256, state, full_text, char_count, raw_output, "
            "block_count, quality_flags_json, attempt_count, qa_state, page_type, layout_type, "
            "primary_text, selected_engine, published_text, index_eligible, updated_at) "
            "VALUES (?, ?, ?, 'passed', ?, ?, NULL, 0, '[]', 0, 'not_required', ?, ?, ?, "
            "'primary', ?, ?, datetime('now', '+9 hours'))",
            (
                legacy_run_id,
                page_no,
                input_page.image_sha256,
                published_text,
                len(published_text),
                page_type,
                "normal_prose" if page_type == "narrative" else "structured",
                published_text,
                published_text,
                index_eligible,
            ),
        )

    conn.execute(
        "INSERT INTO ocr_publications "
        "(book_id, run_id, superseded_publication_id, action, actor, note, published_at) "
        "VALUES (?, ?, NULL, 'legacy_snapshot', ?, ?, datetime('now', '+9 hours'))",
        (book_id, legacy_run_id, actor, "canonical pages before first versioned OCR publication"),
    )
    return legacy_run_id


def publish_pages(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    run_id: int,
    pages: list[PublicationPage],
    actor: str,
    action: str,
    note: str | None,
) -> None:
    """Materialize a complete run and append an active-publication event."""
    if not pages:
        raise ValueError("cannot publish an empty OCR run")
    expected_page_numbers = list(range(1, len(pages) + 1))
    actual_page_numbers = [page.page_no for page in pages]
    if actual_page_numbers != expected_page_numbers:
        raise ValueError(f"publication pages must be contiguous from 1: found {actual_page_numbers}")

    for page in pages:
        conn.execute(
            "UPDATE ocr_page_results SET published_text=? WHERE run_id=? AND page_no=?",
            (page.published_text, run_id, page.page_no),
        )
        conn.execute(
            """
            INSERT INTO pages (
                book_id, page_no, image_path, full_text, char_count,
                page_type, index_eligible
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id, page_no) DO UPDATE SET
                image_path=excluded.image_path,
                full_text=excluded.full_text,
                char_count=excluded.char_count,
                page_type=excluded.page_type,
                index_eligible=excluded.index_eligible
            """,
            (
                book_id,
                page.page_no,
                page.image_path,
                page.published_text,
                len(page.published_text),
                page.page_type,
                page.index_eligible,
            ),
        )
    conn.execute("DELETE FROM pages WHERE book_id=? AND page_no > ?", (book_id, len(pages)))
    conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")

    superseded_id = _active_publication_id(conn, book_id)
    if superseded_id is not None:
        conn.execute(
            "UPDATE ocr_publications SET retired_at=datetime('now', '+9 hours') WHERE id=? AND retired_at IS NULL",
            (superseded_id,),
        )
    conn.execute(
        "INSERT INTO ocr_publications "
        "(book_id, run_id, superseded_publication_id, action, actor, note, published_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now', '+9 hours'))",
        (book_id, run_id, superseded_id, action, actor, note),
    )


def activate_published_run(run_id: int, actor: str, note: str | None = None) -> None:
    """Re-activate an approved materialized run, including legacy rollback."""
    with with_db() as conn:
        run = conn.execute(
            "SELECT book_name, source_page_count, state, qa_state FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        if (str(run[2]), str(run[3])) != ("completed", "approved"):
            raise ValueError("only completed and approved OCR runs can be activated")
        book_name = str(run[0])
        input_pages = collect_input_pages(book_name)
        if int(run[1]) != len(input_pages):
            raise ValueError("OCR source page count changed before activation")

        rows = conn.execute(
            "SELECT page_no, image_sha256, published_text, page_type, index_eligible "
            "FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (run_id,),
        ).fetchall()
        if len(rows) != len(input_pages):
            raise ValueError(f"OCR run is incomplete: {len(rows)}/{len(input_pages)} pages")

        pages: list[PublicationPage] = []
        for input_page, row in zip(input_pages, rows, strict=True):
            if int(row[0]) != input_page.page_no or str(row[1]) != input_page.image_sha256:
                raise ValueError(f"source image changed during OCR: page {input_page.page_no}")
            if row[2] is None:
                raise ValueError(f"OCR run has no materialized published text: page {input_page.page_no}")
            pages.append(
                PublicationPage(
                    page_no=input_page.page_no,
                    image_path=str(input_page.image_path),
                    image_sha256=input_page.image_sha256,
                    published_text=str(row[2]),
                    page_type=str(row[3]),
                    index_eligible=bool(row[4]),
                )
            )

        with conn:
            book = conn.execute("SELECT id FROM books WHERE name=?", (book_name,)).fetchone()
            if book is None:
                raise LookupError(f"book not found for OCR run: {book_name}")
            book_id = int(book[0])
            conn.execute(
                "UPDATE books SET images_dir=?, page_count=?, indexed_at=NULL, "
                "ocr_done_at=datetime('now', '+9 hours') WHERE id=?",
                (str(input_pages[0].image_path.parent), len(input_pages), book_id),
            )
            publish_pages(
                conn,
                book_id=book_id,
                run_id=run_id,
                pages=pages,
                actor=actor,
                action="rollback",
                note=note,
            )


def snapshot_legacy_from_manifest(
    *,
    db_path: Path,
    images_root: Path,
    manifest: dict[str, Any],
    actor: str,
    backup_reference: str,
) -> dict[str, int]:
    """Create all canonical legacy snapshots in one transaction."""
    if not backup_reference.strip():
        raise ValueError("a verified backup reference is required")
    images_root = images_root.resolve(strict=True)
    created = 0
    existing = 0
    with open_db(str(db_path)) as conn, conn:
        for book in manifest["books"]:
            if not bool(book["has_canonical_ocr"]):
                continue
            book_name = str(book["book_name"])
            row = conn.execute("SELECT id FROM books WHERE name=?", (book_name,)).fetchone()
            if row is None:
                raise ValueError(f"canonical book disappeared after manifest creation: {book_name}")
            input_pages: list[OcrInputPage] = []
            for page in book["pages"]:
                image_path = (images_root / str(page["image_path"])).resolve(strict=True)
                if not image_path.is_relative_to(images_root):
                    raise ValueError("manifest image escaped images root")
                input_pages.append(
                    OcrInputPage(
                        page_no=int(page["page_no"]),
                        image_path=image_path,
                        image_sha256=str(page["image_sha256"]),
                    )
                )
            active_before = _active_publication_id(conn, int(row[0]))
            ensure_legacy_snapshot(
                conn,
                book_id=int(row[0]),
                book_name=book_name,
                input_pages=input_pages,
                actor=actor,
            )
            if active_before is None:
                created += 1
            else:
                existing += 1
        conn.execute(
            "UPDATE ocr_publications SET note=note || ? "
            "WHERE action='legacy_snapshot' AND retired_at IS NULL AND note NOT LIKE ?",
            (f"; verified backup={backup_reference}", f"%verified backup={backup_reference}%"),
        )
    return {"created": created, "existing": existing}
