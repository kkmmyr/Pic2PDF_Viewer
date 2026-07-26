"""Page-level OCR checkpoints and atomic publication to canonical pages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import config
from utils.path_utils import resolve_under_base, validate_safe_name

from .connection import with_db
from .extractor import OcrPageResult, OcrTask
from .ocr_page_types import is_index_eligible, suggest_page_type, validate_page_type

_QA_AUDIT_ONLY_FLAGS = frozenset(
    {
        "cross_engine_consensus",
        "yomitoku_adjudication",
    }
)


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
                attempt_count, error_message, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '+9 hours'))
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


def _validate_passed_run(
    run_id: int,
    input_pages: list[OcrInputPage],
) -> tuple[str, list]:
    """Validate source immutability and return the complete passed page rows."""
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
            "page_type, index_eligible "
            "FROM ocr_page_results WHERE run_id = ? ORDER BY page_no",
            (run_id,),
        ).fetchall()
        if len(rows) != len(input_pages):
            raise ValueError(f"OCR run is incomplete: {len(rows)}/{len(input_pages)} pages")
        for row in rows:
            page_no = int(row[0])
            if row[2] != "passed":
                detail = f", {row[5]}" if row[5] else ""
                raise ValueError(f"OCR quality gate failed on page {page_no}: state={row[2]}{detail}")
            if expected_hashes.get(page_no) != row[1]:
                raise ValueError(f"source image changed during OCR: page {page_no}")
    return book_name, rows


def classify_run_pages(run_id: int, *, overwrite: bool = False) -> dict[str, int]:
    """Apply conservative page-type suggestions to an OCR run."""
    with with_db() as conn:
        run = conn.execute(
            "SELECT source_page_count FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        page_count = int(run[0])
        rows = conn.execute(
            "SELECT page_no, full_text, char_count, page_type FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (run_id,),
        ).fetchall()
        counts = {page_type: 0 for page_type in ("unknown", "narrative", "toc", "illustration", "colophon_or_ad")}
        with conn:
            for row in rows:
                current_type = str(row[3] or "unknown")
                page_type = (
                    suggest_page_type(
                        page_no=int(row[0]),
                        page_count=page_count,
                        full_text=str(row[1] or ""),
                        char_count=int(row[2] or 0),
                    )
                    if overwrite or current_type == "unknown"
                    else validate_page_type(current_type)
                )
                counts[page_type] += 1
                conn.execute(
                    "UPDATE ocr_page_results SET page_type=?, index_eligible=? WHERE run_id=? AND page_no=?",
                    (page_type, is_index_eligible(page_type), run_id, int(row[0])),
                )
            conn.execute(
                "UPDATE ocr_page_results SET qa_state='required', qa_note=NULL, reviewed_at=NULL "
                "WHERE run_id=? AND page_type='unknown'",
                (run_id,),
            )
    return counts


def stage_run_for_qa(run_id: int, input_pages: list[OcrInputPage]) -> None:
    """Move a fully passed OCR run to QA without publishing canonical text."""
    _, rows = _validate_passed_run(run_id, input_pages)
    classify_run_pages(run_id)
    flagged_pages = {int(row[0]) for row in rows if set(json.loads(str(row[6]))) - _QA_AUDIT_ONLY_FLAGS}
    page_count = len(input_pages)
    required_pages = set(range(1, min(7, page_count) + 1)) | flagged_pages
    required_pages.update({min(8, page_count), max(1, (page_count + 1) // 2), page_count})
    with with_db() as conn:
        with conn:
            conn.execute(
                "UPDATE ocr_page_results SET qa_state='not_required', qa_note=NULL, reviewed_at=NULL WHERE run_id=?",
                (run_id,),
            )
            conn.executemany(
                "UPDATE ocr_page_results SET qa_state='required' WHERE run_id=? AND page_no=?",
                [(run_id, page_no) for page_no in sorted(required_pages)],
            )
            conn.execute(
                "UPDATE ocr_page_results SET qa_state='required' WHERE run_id=? AND page_type='unknown'",
                (run_id,),
            )
            conn.execute(
                "UPDATE ocr_runs SET state='awaiting_qa', qa_state='pending', finished_at=NULL, "
                "error_message=NULL, qa_reviewer=NULL, qa_reviewed_at=NULL, qa_note=NULL WHERE id=?",
                (run_id,),
            )


def review_qa_page(
    run_id: int,
    page_no: int,
    state: str,
    note: str | None,
    page_type: str,
) -> None:
    if state not in {"approved", "rejected"}:
        raise ValueError("QA page state must be approved or rejected")
    validate_page_type(page_type)
    if state == "approved" and page_type == "unknown":
        raise ValueError("page type must be classified before approval")
    with with_db() as conn:
        run = conn.execute("SELECT state FROM ocr_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        if run[0] != "awaiting_qa":
            raise ValueError("OCR run is not awaiting QA")
        cursor = conn.execute(
            "UPDATE ocr_page_results SET qa_state=?, qa_note=?, page_type=?, index_eligible=?, "
            "reviewed_at=datetime('now', '+9 hours') WHERE run_id=? AND page_no=?",
            (state, note, page_type, is_index_eligible(page_type), run_id, page_no),
        )
        if cursor.rowcount != 1:
            raise LookupError(f"OCR page not found: run={run_id}, page={page_no}")
        conn.commit()


def list_qa_runs() -> list[dict]:
    with with_db() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.book_name, r.engine, r.model, r.source_page_count,
                   r.state, r.qa_state, r.started_at,
                   SUM(CASE WHEN p.qa_state='required' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN p.qa_state='approved' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN p.qa_state='rejected' THEN 1 ELSE 0 END)
            FROM ocr_runs r
            LEFT JOIN ocr_page_results p ON p.run_id=r.id
            WHERE r.state IN ('awaiting_qa', 'completed')
            GROUP BY r.id
            ORDER BY CASE WHEN r.state='awaiting_qa' THEN 0 ELSE 1 END, r.id DESC
            """
        ).fetchall()
    return [
        {
            "id": int(row[0]),
            "book_name": str(row[1]),
            "engine": str(row[2]),
            "model": str(row[3]),
            "source_page_count": int(row[4]),
            "state": str(row[5]),
            "qa_state": str(row[6]),
            "started_at": row[7],
            "required_pages": int(row[8] or 0),
            "approved_pages": int(row[9] or 0),
            "rejected_pages": int(row[10] or 0),
        }
        for row in rows
    ]


def get_qa_run(run_id: int) -> dict:
    with with_db() as conn:
        run = conn.execute(
            "SELECT id, book_name, engine, model, source_page_count, state, qa_state, started_at, "
            "qa_reviewer, qa_reviewed_at, qa_note FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        pages = conn.execute(
            "SELECT page_no, state, qa_state, full_text, char_count, quality_flags_json, "
            "ink_coverage, attempt_count, error_message, qa_note, reviewed_at, "
            "page_type, index_eligible "
            "FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (run_id,),
        ).fetchall()
    required_pages = sum(row[2] == "required" for row in pages)
    approved_pages = sum(row[2] == "approved" for row in pages)
    rejected_pages = sum(row[2] == "rejected" for row in pages)
    return {
        "id": int(run[0]),
        "book_name": str(run[1]),
        "engine": str(run[2]),
        "model": str(run[3]),
        "source_page_count": int(run[4]),
        "state": str(run[5]),
        "qa_state": str(run[6]),
        "started_at": run[7],
        "qa_reviewer": run[8],
        "qa_reviewed_at": run[9],
        "qa_note": run[10],
        "required_pages": required_pages,
        "approved_pages": approved_pages,
        "rejected_pages": rejected_pages,
        "pages": [
            {
                "page_no": int(row[0]),
                "state": str(row[1]),
                "qa_state": str(row[2]),
                "full_text": str(row[3] or ""),
                "char_count": int(row[4] or 0),
                "quality_flags": json.loads(str(row[5] or "[]")),
                "ink_coverage": row[6],
                "attempt_count": int(row[7] or 0),
                "error_message": row[8],
                "qa_note": row[9],
                "reviewed_at": row[10],
                "page_type": str(row[11] or "unknown"),
                "index_eligible": bool(row[12]),
                "image_url": f"/api/ocr/qa/runs/{run_id}/pages/{int(row[0])}/image",
            }
            for row in pages
        ],
    }


def get_qa_image_path(run_id: int, page_no: int) -> Path:
    with with_db() as conn:
        row = conn.execute(
            "SELECT r.book_name, p.image_sha256 FROM ocr_runs r "
            "JOIN ocr_page_results p ON p.run_id=r.id "
            "WHERE r.id=? AND p.page_no=?",
            (run_id, page_no),
        ).fetchone()
    if row is None:
        raise LookupError(f"OCR page not found: run={run_id}, page={page_no}")
    input_pages = collect_input_pages(str(row[0]))
    if page_no < 1 or page_no > len(input_pages):
        raise LookupError(f"OCR page not found: run={run_id}, page={page_no}")
    page = input_pages[page_no - 1]
    if page.image_sha256 != row[1]:
        raise ValueError(f"source image changed after OCR: page {page_no}")
    return page.image_path


def approve_and_publish_run(run_id: int, reviewer: str, note: str | None = None) -> None:
    """Publish only after every required QA page has been explicitly approved."""
    with with_db() as conn:
        run = conn.execute(
            "SELECT book_name, state FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        if run[1] != "awaiting_qa":
            raise ValueError("OCR run is not awaiting QA")
        counts = conn.execute(
            "SELECT "
            "SUM(CASE WHEN qa_state='required' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN qa_state='rejected' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN page_type='unknown' THEN 1 ELSE 0 END) "
            "FROM ocr_page_results WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if int(counts[0] or 0) > 0:
            raise ValueError("required QA pages remain")
        if int(counts[1] or 0) > 0:
            raise ValueError("rejected QA pages remain")
        if int(counts[2] or 0) > 0:
            raise ValueError("unclassified OCR pages remain")
        book_name = str(run[0])

    input_pages = collect_input_pages(book_name)
    book_name, rows = _validate_passed_run(run_id, input_pages)
    _publish_rows(run_id, book_name, rows, input_pages, reviewer, note)


def _publish_rows(
    run_id: int,
    book_name: str,
    rows: list,
    input_pages: list[OcrInputPage],
    reviewer: str,
    note: str | None,
) -> None:
    """Atomically publish validated rows and mark the run QA-approved."""
    with with_db() as conn:
        images_dir = input_pages[0].image_path.parent
        with conn:
            existing = conn.execute("SELECT id FROM books WHERE name = ?", (book_name,)).fetchone()
            if existing is None:
                cursor = conn.execute(
                    "INSERT INTO books "
                    "(name, pdf_path, images_dir, page_count, indexed_at, ocr_done_at) "
                    "VALUES (?, '', ?, ?, NULL, datetime('now', '+9 hours'))",
                    (book_name, str(images_dir), len(input_pages)),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("failed to create book during OCR publication")
                book_id = cursor.lastrowid
            else:
                book_id = int(existing[0])
                conn.execute(
                    "UPDATE books SET images_dir=?, page_count=?, indexed_at=NULL, "
                    "ocr_done_at=datetime('now', '+9 hours') WHERE id=?",
                    (str(images_dir), len(input_pages), book_id),
                )

            for row in rows:
                page_no = int(row[0])
                image_path = input_pages[page_no - 1].image_path
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
                        page_no,
                        str(image_path),
                        row[3] or "",
                        int(row[4] or 0),
                        str(row[7]),
                        bool(row[8]),
                    ),
                )
            conn.execute(
                "DELETE FROM pages WHERE book_id=? AND page_no > ?",
                (book_id, len(input_pages)),
            )
            # pages_fts is an external-content FTS5 table.  A direct DELETE for a
            # row that was not indexed yet can corrupt a fresh index, so rebuild
            # from the canonical pages table inside the publication transaction.
            conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
            conn.execute(
                "UPDATE ocr_runs SET state='completed', finished_at=datetime('now', '+9 hours'), "
                "error_message=NULL, qa_state='approved', qa_reviewer=?, "
                "qa_reviewed_at=datetime('now', '+9 hours'), qa_note=? WHERE id=?",
                (reviewer, note, run_id),
            )
