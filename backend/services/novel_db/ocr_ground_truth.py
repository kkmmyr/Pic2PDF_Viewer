"""Human-verified OCR ground-truth corpus and CER evaluation."""

from __future__ import annotations

import hashlib
import re
from typing import TypedDict

from .connection import with_db
from .ocr_layout_types import validate_layout_type
from .ocr_page_types import validate_page_type
from .ocr_run_store import collect_input_pages

_METRIC_PAGE_TYPE_ORDER = (
    "narrative",
    "toc",
    "illustration",
    "colophon_or_ad",
    "unknown",
)
_METRIC_LAYOUT_TYPE_ORDER = (
    "normal_prose",
    "full_width",
    "mixed_illustration",
    "structured",
    "image_only",
    "unknown",
)


class GroundTruthSample(TypedDict):
    run_id: int
    page_no: int


def _edit_distance(reference: str, hypothesis: str) -> int:
    """Return exact Levenshtein distance using Python's arbitrary-width bitsets."""
    if not reference:
        return len(hypothesis)
    if not hypothesis:
        return len(reference)
    if len(reference) > len(hypothesis):
        reference, hypothesis = hypothesis, reference

    width = len(reference)
    mask = (1 << width) - 1
    highest_bit = 1 << (width - 1)
    character_masks: dict[str, int] = {}
    for index, character in enumerate(reference):
        character_masks[character] = character_masks.get(character, 0) | (1 << index)

    positive = mask
    negative = 0
    distance = width
    for character in hypothesis:
        equal = character_masks.get(character, 0)
        vertical = equal | negative
        horizontal = (((equal & positive) + positive) ^ positive) | equal
        positive_horizontal = negative | ~(horizontal | positive)
        negative_horizontal = positive & horizontal
        if positive_horizontal & highest_bit:
            distance += 1
        elif negative_horizontal & highest_bit:
            distance -= 1
        positive_horizontal = ((positive_horizontal << 1) | 1) & mask
        negative_horizontal = (negative_horizontal << 1) & mask
        positive = (negative_horizontal | ~(vertical | positive_horizontal)) & mask
        negative = positive_horizontal & vertical
    return distance


def _normalize_metric_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _metric_sha256(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def _metric_fingerprints(reference: str, hypothesis: str) -> tuple[str, str]:
    return (
        _metric_sha256(_normalize_metric_text(reference)),
        _metric_sha256(_normalize_metric_text(hypothesis)),
    )


def _cached_metric_values(reference: str, hypothesis: str) -> tuple[str, str, int, int, float | None]:
    normalized_reference = _normalize_metric_text(reference)
    normalized_hypothesis = _normalize_metric_text(hypothesis)
    distance = _edit_distance(normalized_reference, normalized_hypothesis)
    reference_chars = len(normalized_reference)
    return (
        _metric_sha256(normalized_reference),
        _metric_sha256(normalized_hypothesis),
        distance,
        reference_chars,
        distance / reference_chars if reference_chars else None,
    )


def character_error_rate(reference: str, hypothesis: str) -> tuple[int, int, float | None]:
    _reference_sha, _hypothesis_sha, distance, reference_chars, cer = _cached_metric_values(reference, hypothesis)
    return distance, reference_chars, cer


def seed_ground_truth(samples: list[GroundTruthSample]) -> int:
    """Create draft entries from existing OCR runs without treating OCR as truth."""
    created = 0
    with with_db() as conn:
        with conn:
            for sample in samples:
                row = conn.execute(
                    "SELECT r.book_name, p.image_sha256, p.page_type, p.layout_type "
                    "FROM ocr_runs r JOIN ocr_page_results p ON p.run_id=r.id "
                    "WHERE r.id=? AND p.page_no=?",
                    (sample["run_id"], sample["page_no"]),
                ).fetchone()
                if row is None:
                    raise LookupError(f"OCR page not found: run={sample['run_id']}, page={sample['page_no']}")
                cursor = conn.execute(
                    """
                    INSERT INTO ocr_ground_truth_pages (
                        run_id, page_no, image_sha256, page_type, layout_type,
                        state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'draft',
                              datetime('now', '+9 hours'), datetime('now', '+9 hours'))
                    ON CONFLICT(run_id, page_no) DO NOTHING
                    """,
                    (
                        sample["run_id"],
                        sample["page_no"],
                        str(row[1]),
                        str(row[2] or "unknown"),
                        str(row[3] or "unknown"),
                    ),
                )
                created += cursor.rowcount
    return created


def update_ground_truth(
    entry_id: int,
    *,
    reference_text: str | None,
    page_type: str,
    layout_type: str,
    state: str,
    note: str | None,
) -> None:
    validate_page_type(page_type)
    validate_layout_type(layout_type)
    if state not in {"draft", "verified"}:
        raise ValueError("ground-truth state must be draft or verified")
    if state == "verified":
        if page_type == "unknown":
            raise ValueError("verified ground truth requires a classified page type")
        if layout_type == "unknown":
            raise ValueError("verified ground truth requires a classified layout type")
        if not (reference_text or "").strip():
            raise ValueError("verified ground truth requires reference text")

    with with_db() as conn:
        row = conn.execute(
            "SELECT g.run_id, g.page_no, g.image_sha256, r.book_name, p.full_text "
            "FROM ocr_ground_truth_pages g JOIN ocr_runs r ON r.id=g.run_id "
            "JOIN ocr_page_results p ON p.run_id=g.run_id AND p.page_no=g.page_no "
            "WHERE g.id=?",
            (entry_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"ground-truth entry not found: {entry_id}")
        input_pages = collect_input_pages(str(row[3]))
        page_no = int(row[1])
        if page_no < 1 or page_no > len(input_pages):
            raise ValueError(f"source page no longer exists: page {page_no}")
        if input_pages[page_no - 1].image_sha256 != row[2]:
            raise ValueError(f"source image changed after corpus entry creation: page {page_no}")
        if state == "verified":
            reference_sha, hypothesis_sha, distance, reference_chars, _cer = _cached_metric_values(
                str(reference_text or ""), str(row[4] or "")
            )
            cursor = conn.execute(
                """
                UPDATE ocr_ground_truth_pages
                SET reference_text=?, page_type=?, layout_type=?, state=?, note=?,
                    updated_at=datetime('now', '+9 hours'),
                    verified_at=datetime('now', '+9 hours'),
                    cer_reference_sha256=?, cer_hypothesis_sha256=?,
                    cer_edit_distance=?, cer_reference_chars=?
                WHERE id=?
                """,
                (
                    reference_text,
                    page_type,
                    layout_type,
                    state,
                    note,
                    reference_sha,
                    hypothesis_sha,
                    distance,
                    reference_chars,
                    entry_id,
                ),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE ocr_ground_truth_pages
                SET reference_text=?, page_type=?, layout_type=?, state=?, note=?,
                    updated_at=datetime('now', '+9 hours'), verified_at=NULL,
                    cer_reference_sha256=NULL, cer_hypothesis_sha256=NULL,
                    cer_edit_distance=NULL, cer_reference_chars=NULL
                WHERE id=?
                """,
                (reference_text, page_type, layout_type, state, note, entry_id),
            )
        if cursor.rowcount != 1:
            raise LookupError(f"ground-truth entry not found: {entry_id}")
        conn.commit()


def list_ground_truth() -> dict:
    with with_db() as conn:
        rows = conn.execute(
            """
            SELECT g.id, g.run_id, g.page_no, g.image_sha256, g.page_type,
                   g.layout_type, g.reference_text, g.state, g.note, g.created_at,
                   g.updated_at, g.verified_at, r.book_name, p.full_text,
                   g.cer_reference_sha256, g.cer_hypothesis_sha256,
                   g.cer_edit_distance, g.cer_reference_chars
            FROM ocr_ground_truth_pages g
            JOIN ocr_runs r ON r.id=g.run_id
            JOIN ocr_page_results p ON p.run_id=g.run_id AND p.page_no=g.page_no
            ORDER BY g.run_id, g.page_no
            """
        ).fetchall()

    entries = []
    stale_metrics: list[tuple[str, str, int, int, int]] = []
    total_distance = 0
    total_reference_chars = 0
    verified_count = 0
    metrics_by_page_type = {
        page_type: {
            "page_type": page_type,
            "total_count": 0,
            "verified_count": 0,
            "total_edit_distance": 0,
            "total_reference_chars": 0,
        }
        for page_type in _METRIC_PAGE_TYPE_ORDER
    }
    metrics_by_layout_type = {
        layout_type: {
            "layout_type": layout_type,
            "total_count": 0,
            "verified_count": 0,
            "total_edit_distance": 0,
            "total_reference_chars": 0,
        }
        for layout_type in _METRIC_LAYOUT_TYPE_ORDER
    }
    for row in rows:
        reference_text = str(row[6] or "")
        ocr_text = str(row[13] or "")
        page_type = str(row[4])
        layout_type = str(row[5])
        page_type_metrics = metrics_by_page_type[page_type]
        layout_type_metrics = metrics_by_layout_type[layout_type]
        page_type_metrics["total_count"] += 1
        layout_type_metrics["total_count"] += 1
        distance = None
        reference_chars = None
        cer = None
        if row[7] == "verified":
            verified_count += 1
            reference_sha, hypothesis_sha = _metric_fingerprints(reference_text, ocr_text)
            if row[14] == reference_sha and row[15] == hypothesis_sha and row[16] is not None and row[17] is not None:
                distance = int(row[16])
                reference_chars = int(row[17])
                cer = distance / reference_chars if reference_chars else None
            else:
                distance, reference_chars, cer = character_error_rate(reference_text, ocr_text)
                stale_metrics.append((reference_sha, hypothesis_sha, distance, reference_chars, int(row[0])))
            total_distance += distance
            total_reference_chars += reference_chars
            page_type_metrics["verified_count"] += 1
            page_type_metrics["total_edit_distance"] += distance
            page_type_metrics["total_reference_chars"] += reference_chars
            layout_type_metrics["verified_count"] += 1
            layout_type_metrics["total_edit_distance"] += distance
            layout_type_metrics["total_reference_chars"] += reference_chars
        entries.append(
            {
                "id": int(row[0]),
                "run_id": int(row[1]),
                "page_no": int(row[2]),
                "image_sha256": str(row[3]),
                "page_type": str(row[4]),
                "layout_type": str(row[5]),
                "reference_text": reference_text,
                "state": str(row[7]),
                "note": row[8],
                "created_at": row[9],
                "updated_at": row[10],
                "verified_at": row[11],
                "book_name": str(row[12]),
                "ocr_text": ocr_text,
                "edit_distance": distance,
                "reference_chars": reference_chars,
                "cer": cer,
                "image_url": f"/api/ocr/ground-truth/{int(row[0])}/image",
            }
        )
    if stale_metrics:
        with with_db() as conn:
            with conn:
                conn.executemany(
                    """
                    UPDATE ocr_ground_truth_pages
                    SET cer_reference_sha256=?, cer_hypothesis_sha256=?,
                        cer_edit_distance=?, cer_reference_chars=?
                    WHERE id=? AND state='verified'
                    """,
                    stale_metrics,
                )

    aggregate_cer = total_distance / total_reference_chars if total_reference_chars else None
    page_type_metrics_list = []
    for page_type in _METRIC_PAGE_TYPE_ORDER:
        metrics = metrics_by_page_type[page_type]
        reference_chars = metrics["total_reference_chars"]
        page_type_metrics_list.append(
            {
                **metrics,
                "aggregate_cer": (metrics["total_edit_distance"] / reference_chars if reference_chars else None),
            }
        )
    layout_type_metrics_list = []
    for layout_type in _METRIC_LAYOUT_TYPE_ORDER:
        metrics = metrics_by_layout_type[layout_type]
        reference_chars = metrics["total_reference_chars"]
        layout_type_metrics_list.append(
            {
                **metrics,
                "aggregate_cer": (metrics["total_edit_distance"] / reference_chars if reference_chars else None),
            }
        )
    return {
        "entries": entries,
        "total_count": len(entries),
        "verified_count": verified_count,
        "total_edit_distance": total_distance,
        "total_reference_chars": total_reference_chars,
        "aggregate_cer": aggregate_cer,
        "metrics_by_page_type": page_type_metrics_list,
        "metrics_by_layout_type": layout_type_metrics_list,
    }


def get_ground_truth_image_path(entry_id: int):
    with with_db() as conn:
        row = conn.execute(
            "SELECT run_id, page_no FROM ocr_ground_truth_pages WHERE id=?",
            (entry_id,),
        ).fetchone()
    if row is None:
        raise LookupError(f"ground-truth entry not found: {entry_id}")
    from .ocr_qa_queries import get_qa_image_path

    return get_qa_image_path(int(row[0]), int(row[1]))
