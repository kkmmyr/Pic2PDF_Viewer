"""Durable OCR run storage and source-image validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import config
from utils.path_utils import resolve_under_base, validate_safe_name

from .connection import with_db
from .extractor import OcrPageResult, OcrTask


@dataclass(frozen=True)
class OcrInputPage:
    page_no: int
    image_path: Path
    image_sha256: str


def collect_input_pages(book_name: str) -> list[OcrInputPage]:
    validate_safe_name(book_name, param_name="book_name")
    images_dir = Path(
        resolve_under_base(
            config.KINDLE_NOVEL_IMAGES_DIR,
            book_name,
            param_name="book_name",
        )
    )
    if not images_dir.is_dir():
        raise FileNotFoundError(f"images dir not found: {images_dir}")

    numbered: list[tuple[int, Path]] = []
    for image_path in images_dir.glob("*.png"):
        if image_path.stem.isdigit():
            numbered.append((int(image_path.stem), image_path))
    numbered.sort(key=lambda item: item[0])
    if not numbered:
        raise ValueError(f"no numbered PNG images found in: {images_dir}")

    page_numbers = [page_no for page_no, _ in numbered]
    expected = list(range(1, len(numbered) + 1))
    if page_numbers != expected:
        raise ValueError(f"PNG page numbers must be contiguous from 1: found {page_numbers}")

    pages: list[OcrInputPage] = []
    for page_no, image_path in numbered:
        with image_path.open("rb") as image_file:
            image_sha256 = hashlib.file_digest(image_file, "sha256").hexdigest()
        pages.append(OcrInputPage(page_no, image_path, image_sha256))
    return pages


def prepare_run(
    book_name: str,
    engine: str,
    model: str,
    input_pages: list[OcrInputPage],
) -> tuple[int, list[OcrTask]]:
    """Resume a compatible unfinished run and return only pages needing work."""
    with with_db() as conn:
        row = conn.execute(
            "SELECT id FROM ocr_runs "
            "WHERE book_name = ? AND engine = ? AND model = ? AND source_page_count = ? "
            "AND state IN ('running', 'failed') ORDER BY id DESC LIMIT 1",
            (book_name, engine, model, len(input_pages)),
        ).fetchone()
        with conn:
            if row is None:
                cursor = conn.execute(
                    "INSERT INTO ocr_runs "
                    "(book_name, engine, model, source_page_count, state, started_at) "
                    "VALUES (?, ?, ?, ?, 'running', datetime('now', '+9 hours'))",
                    (book_name, engine, model, len(input_pages)),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("failed to create OCR run")
                run_id = cursor.lastrowid
            else:
                run_id = int(row[0])
                conn.execute(
                    "UPDATE ocr_runs SET state='running', finished_at=NULL, error_message=NULL WHERE id = ?",
                    (run_id,),
                )

        passed_rows = conn.execute(
            "SELECT page_no, image_sha256 FROM ocr_page_results WHERE run_id = ? AND state = 'passed'",
            (run_id,),
        ).fetchall()
    passed_hashes = {int(row[0]): str(row[1]) for row in passed_rows}
    tasks: list[OcrTask] = []
    for page in input_pages:
        if passed_hashes.get(page.page_no) == page.image_sha256:
            continue
        tasks.append({"book_name": book_name, "page_no": page.page_no, "image_path": str(page.image_path)})
    return run_id, tasks


def save_page_result(run_id: int, page: OcrPageResult) -> None:
    with with_db() as conn:
        conn.execute(
            """
            INSERT INTO ocr_page_results (
                run_id, page_no, image_sha256, state, full_text, char_count,
                raw_output, block_count, quality_flags_json, ink_coverage,
                attempt_count, error_message, layout_type, primary_text,
                external_text, selected_engine, selection_reason, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      datetime('now', '+9 hours'))
            ON CONFLICT(run_id, page_no) DO UPDATE SET
                image_sha256 = excluded.image_sha256,
                state = excluded.state,
                full_text = excluded.full_text,
                char_count = excluded.char_count,
                raw_output = excluded.raw_output,
                block_count = excluded.block_count,
                quality_flags_json = excluded.quality_flags_json,
                ink_coverage = excluded.ink_coverage,
                attempt_count = excluded.attempt_count,
                error_message = excluded.error_message,
                layout_type = excluded.layout_type,
                primary_text = excluded.primary_text,
                external_text = excluded.external_text,
                selected_engine = excluded.selected_engine,
                selection_reason = excluded.selection_reason,
                corrected_text = NULL,
                updated_at = excluded.updated_at
            """,
            (
                run_id,
                page["page_no"],
                page["image_sha256"],
                page["state"],
                page["full_text"],
                page["char_count"],
                page["raw_output"],
                page["block_count"],
                json.dumps(page["quality_flags"], ensure_ascii=False),
                page["ink_coverage"],
                page["attempt_count"],
                page.get("error_message"),
                page.get("layout_type", "unknown"),
                page.get("primary_text"),
                page.get("external_text"),
                page.get("selected_engine", "primary"),
                page.get("selection_reason"),
            ),
        )
        conn.commit()


def mark_run_failed(run_id: int, error: str) -> None:
    with with_db() as conn:
        conn.execute(
            "UPDATE ocr_runs SET state='failed', finished_at=datetime('now', '+9 hours'), error_message=? WHERE id=?",
            (error, run_id),
        )
        conn.commit()


def validate_complete_run(
    run_id: int,
    input_pages: list[OcrInputPage],
) -> tuple[str, list]:
    """Validate source immutability and return all durable page rows."""
    expected_hashes = {page.page_no: page.image_sha256 for page in input_pages}
    for page in input_pages:
        with page.image_path.open("rb") as image_file:
            current_hash = hashlib.file_digest(image_file, "sha256").hexdigest()
        if current_hash != page.image_sha256:
            raise ValueError(f"source image changed during OCR: page {page.page_no}")
    with with_db() as conn:
        run = conn.execute(
            "SELECT book_name, source_page_count FROM ocr_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise ValueError(f"OCR run not found: {run_id}")
        book_name = str(run[0])
        if int(run[1]) != len(input_pages):
            raise ValueError("OCR source page count changed before publication")

        rows = conn.execute(
            "SELECT page_no, image_sha256, state, full_text, char_count, error_message, quality_flags_json, "
            "page_type, index_eligible, layout_type, primary_text, external_text, selected_engine, corrected_text "
            "FROM ocr_page_results WHERE run_id = ? ORDER BY page_no",
            (run_id,),
        ).fetchall()
        if len(rows) != len(input_pages):
            raise ValueError(f"OCR run is incomplete: {len(rows)}/{len(input_pages)} pages")
        for row in rows:
            page_no = int(row[0])
            if expected_hashes.get(page_no) != row[1]:
                raise ValueError(f"source image changed during OCR: page {page_no}")
    return book_name, rows
