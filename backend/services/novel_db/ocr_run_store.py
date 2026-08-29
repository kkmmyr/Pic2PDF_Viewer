"""Durable OCR run storage and source-image validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config
from utils.path_utils import resolve_under_base, validate_safe_name

from .connection import with_db
from .extractor import OcrPageResult, OcrTask
from .ocr_provenance import candidate_manifest, canonical_json, validate_model_revision


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
    model = validate_model_revision(model)
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
    primary_text = str(page.get("primary_text") or page["full_text"] or "")
    external_text = page.get("external_text")
    selected_engine = str(page.get("selected_engine", "primary"))
    if selected_engine not in {"primary", "external"}:
        raise ValueError("worker selected engine must be primary or external")
    if selected_engine == "external" and not str(external_text or "").strip():
        raise ValueError("selected external OCR candidate is empty")

    primary_raw_output = page.get("primary_raw_output")
    if primary_raw_output is None:
        primary_raw_output = page["raw_output"] if selected_engine == "primary" else ""
    external_raw_output = page.get("external_raw_output")
    expected_candidates = candidate_manifest(
        primary_text=primary_text,
        primary_raw_output=str(primary_raw_output or ""),
        primary_state=page["state"],
        primary_block_count=page["block_count"],
        primary_quality_flags=page["quality_flags"],
        primary_attempt_count=page["attempt_count"],
        external_text=str(external_text) if external_text is not None else None,
        external_raw_output=str(external_raw_output or "") if external_text is not None else None,
        external_state=None,
        external_block_count=None,
        external_quality_flags=None,
        external_attempt_count=None,
    )
    candidate_json = _candidate_manifest_json(
        page,
        expected_candidates,
        primary_text,
        external_text,
        selected_engine,
    )

    processing_timing = _validate_timing(page.get("processing_timing") or {}, "processing timing")
    with with_db() as conn:
        _save_run_provenance(
            conn,
            run_id,
            page.get("runtime_manifest"),
            page.get("run_timing") or {},
        )
        conn.execute(
            """
            INSERT INTO ocr_page_results (
                run_id, page_no, image_sha256, state, full_text, char_count,
                raw_output, block_count, quality_flags_json, ink_coverage,
                attempt_count, error_message, layout_type, primary_text,
                external_text, primary_raw_output, external_raw_output,
                candidate_manifest_json, processing_timing_json, selected_engine,
                selection_reason, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
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
                primary_raw_output = excluded.primary_raw_output,
                external_raw_output = excluded.external_raw_output,
                candidate_manifest_json = excluded.candidate_manifest_json,
                processing_timing_json = excluded.processing_timing_json,
                selected_engine = excluded.selected_engine,
                selection_reason = excluded.selection_reason,
                corrected_text = NULL,
                review_started_at = NULL,
                review_duration_ms = NULL,
                correction_duration_ms = NULL,
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
                primary_text,
                external_text,
                primary_raw_output,
                external_raw_output,
                candidate_json,
                canonical_json(processing_timing),
                selected_engine,
                page.get("selection_reason"),
            ),
        )
        conn.commit()


def _validate_candidate_entry(label: str, supplied: object, expected: object) -> None:
    if not isinstance(supplied, dict) or not isinstance(expected, dict):
        raise ValueError(f"candidate manifest {label} entry is required")
    for field in ("text_sha256", "raw_output_sha256"):
        if supplied.get(field) != expected[field]:
            raise ValueError(f"{label} candidate {field} mismatch")


def _candidate_manifest_json(
    page: OcrPageResult,
    expected: dict[str, Any],
    primary_text: str,
    external_text: str | None,
    selected_engine: str,
) -> str:
    supplied = page.get("candidate_manifest")
    if supplied is None:
        return canonical_json(expected)

    _validate_candidate_entry("primary", supplied.get("primary"), expected["primary"])
    supplied_external = supplied.get("external")
    if external_text is None:
        if supplied_external is not None:
            raise ValueError("external candidate manifest exists without external text")
    else:
        _validate_candidate_entry("external", supplied_external, expected["external"])

    selected_text = primary_text if selected_engine == "primary" else external_text
    if page["full_text"] != selected_text:
        raise ValueError("selected OCR text does not match the preserved source candidate")
    return canonical_json(supplied)


def _validate_timing(value: dict, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    timing: dict[str, int] = {}
    for key, duration in value.items():
        if not isinstance(key, str) or isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
            raise ValueError(f"{label} values must be non-negative integer milliseconds")
        timing[key] = duration
    return timing


def _save_run_provenance(conn, run_id: int, runtime_manifest: dict | None, run_timing: dict) -> None:
    row = conn.execute(
        "SELECT model, runtime_manifest_json, timing_json FROM ocr_runs WHERE id=?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"OCR run not found: {run_id}")
    if runtime_manifest is not None:
        if not isinstance(runtime_manifest, dict) or runtime_manifest.get("schema_version") != 1:
            raise ValueError("OCR runtime manifest schema_version must be 1")
        manifest_model = validate_model_revision(str(runtime_manifest.get("model_revision", "")))
        if manifest_model != str(row[0]):
            raise ValueError("OCR runtime manifest model revision does not match the run")
        manifest_json = canonical_json(runtime_manifest)
        stored_manifest = str(row[1] or "{}")
        if stored_manifest not in {"", "{}"} and stored_manifest != manifest_json:
            raise ValueError("OCR runtime manifest changed within the same run")
        if stored_manifest in {"", "{}"}:
            conn.execute(
                "UPDATE ocr_runs SET runtime_manifest_json=? WHERE id=?",
                (manifest_json, run_id),
            )
    timing = _validate_timing(run_timing, "run timing")
    if timing:
        stored_timing = json.loads(str(row[2] or "{}"))
        for key, duration in timing.items():
            stored_timing.setdefault(key, duration)
        conn.execute(
            "UPDATE ocr_runs SET timing_json=? WHERE id=?",
            (canonical_json(stored_timing), run_id),
        )


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
