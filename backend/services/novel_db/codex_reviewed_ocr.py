"""Sealed export and fail-closed staging for Codex-reviewed OCR runs."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from utils.path_utils import validate_safe_name

from .connection import open_db
from .ocr_layout_types import validate_layout_type
from .ocr_page_types import is_index_eligible, validate_page_type
from .qwen_dots_worker import (
    COMPOSITE_MODEL_REVISION,
    DOTS_ENGINE_VERSION,
    DOTS_MODEL_REVISION,
    DOTS_PROMPT_ID,
    DOTS_PROMPT_SHA256,
    QWEN_ENGINE_VERSION,
    QWEN_MODEL_REVISION,
    QWEN_PROMPT_ID,
    QWEN_PROMPT_SHA256,
)

PACKAGE_SCHEMA_VERSION = "codex-reviewed-ocr-package-v1"
IMPORTED_ENGINE = "codex_reviewed_qwen35_dots_v1"
_SOURCE_ENGINE = "qwen35_dots_review_v1"
_PAGE_STATES = frozenset({"approved", "not_required"})
_SELECTED_ENGINES = frozenset({"primary", "external", "codex"})
_REVIEW_METHODS = frozenset({"owner_image_review", "codex_image_review", "machine_audit"})
_PACKAGE_KEYS = frozenset(
    {
        "schema_version",
        "package_sha256",
        "source_run_id",
        "book_name",
        "source_page_count",
        "engine",
        "model",
        "review",
        "pages",
    }
)
_PAGE_KEYS = frozenset(
    {
        "page_no",
        "image_sha256",
        "state",
        "full_text",
        "char_count",
        "raw_output",
        "block_count",
        "quality_flags",
        "ink_coverage",
        "attempt_count",
        "error_message",
        "qa_state",
        "qa_note",
        "reviewed_at",
        "review_method",
        "page_type",
        "index_eligible",
        "layout_type",
        "primary_text",
        "external_text",
        "selected_engine",
        "corrected_text",
        "selection_reason",
    }
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _package_digest(package: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in package.items() if key != "package_sha256"}
    return hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()


def _require_exact_keys(value: dict[str, Any], expected: frozenset[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{label} fields mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _require_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{label} must be a {'string' if allow_empty else 'non-empty string'}")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label} must be a string or null")
    return value


def _validate_sha256(value: Any, label: str) -> str:
    digest = _require_string(value, label)
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return digest


def _selected_text(page: dict[str, Any]) -> str:
    selected_engine = str(page["selected_engine"])
    if selected_engine == "primary":
        return str(page["primary_text"] or page["full_text"] or "")
    if selected_engine == "external":
        return str(page["external_text"] or "")
    if selected_engine == "codex":
        return str(page["corrected_text"] or "")
    return ""


def _review_method(qa_state: str, qa_note: str | None) -> str:
    note = str(qa_note or "")
    if qa_state == "not_required" or note.startswith("machine-assisted clean-page approval"):
        return "machine_audit"
    if note.startswith("owner image review accepted"):
        return "owner_image_review"
    if "Codex" in note or note.startswith("Codex package review attestation:"):
        return "codex_image_review"
    return "owner_image_review"


def _validate_raw_envelope(page: dict[str, Any]) -> None:
    page_no = int(page["page_no"])
    try:
        envelope = json.loads(str(page["raw_output"]))
    except json.JSONDecodeError as exc:
        raise ValueError(f"page {page_no} raw_output is not JSON") from exc
    if not isinstance(envelope, dict) or envelope.get("schema") != "qwen35-dots-page-v1":
        raise ValueError(f"page {page_no} raw_output schema mismatch")
    if envelope.get("selection_reason") != page["selection_reason"]:
        raise ValueError(f"page {page_no} selection reason mismatch")
    for candidate, expected_text, expected_provenance in (
        (
            "primary",
            page["primary_text"],
            (QWEN_MODEL_REVISION, QWEN_ENGINE_VERSION, QWEN_PROMPT_ID, QWEN_PROMPT_SHA256),
        ),
        (
            "external",
            page["external_text"],
            (DOTS_MODEL_REVISION, DOTS_ENGINE_VERSION, DOTS_PROMPT_ID, DOTS_PROMPT_SHA256),
        ),
    ):
        value = envelope.get(candidate)
        if not isinstance(value, dict) or value.get("text") != expected_text:
            raise ValueError(f"page {page_no} {candidate} candidate text mismatch")
        _require_string(value.get("raw_output"), f"page {page_no} {candidate} raw output")
        provenance = value.get("provenance")
        if not isinstance(provenance, dict):
            raise ValueError(f"page {page_no} {candidate} provenance is missing")
        expected_revision, expected_engine, expected_prompt_id, expected_prompt_sha256 = expected_provenance
        expected_fields = {
            "model_revision": expected_revision,
            "engine_version": expected_engine,
            "prompt_id": expected_prompt_id,
            "prompt_sha256": expected_prompt_sha256,
        }
        for field, expected in expected_fields.items():
            if provenance.get(field) != expected:
                raise ValueError(f"page {page_no} {candidate} {field} mismatch")
        _validate_sha256(provenance.get("model_fingerprint"), f"page {page_no} {candidate} model fingerprint")


def _validate_page_result(page: dict[str, Any], page_no: int) -> None:
    _validate_sha256(page["image_sha256"], f"page {page_no} image SHA-256")
    if page["state"] != "passed":
        raise ValueError(f"page {page_no} must be a passed composite result")
    full_text = _require_string(page["full_text"], f"page {page_no} full_text", allow_empty=True)
    if type(page["char_count"]) is not int or page["char_count"] != len(full_text):
        raise ValueError(f"page {page_no} char_count mismatch")
    for field in ("block_count", "attempt_count"):
        if type(page[field]) is not int or page[field] < 0:
            raise ValueError(f"page {page_no} {field} must be a non-negative integer")
    if not isinstance(page["quality_flags"], list) or not all(
        isinstance(flag, str) and flag for flag in page["quality_flags"]
    ):
        raise ValueError(f"page {page_no} quality_flags must be strings")
    if page["ink_coverage"] is not None and not isinstance(page["ink_coverage"], (int, float)):
        raise ValueError(f"page {page_no} ink_coverage must be numeric or null")
    for field in ("error_message", "qa_note", "reviewed_at", "primary_text", "external_text", "corrected_text"):
        _optional_string(page[field], f"page {page_no} {field}")


def _validate_page_review(page: dict[str, Any], page_no: int) -> None:
    if page["qa_state"] not in _PAGE_STATES:
        raise ValueError(f"page {page_no} has unresolved QA state")
    if page["review_method"] not in _REVIEW_METHODS or page["review_method"] != _review_method(
        str(page["qa_state"]), page["qa_note"]
    ):
        raise ValueError(f"page {page_no} review method mismatch")
    if page["qa_state"] == "approved" and not str(page["qa_note"] or "").strip():
        raise ValueError(f"page {page_no} Codex review note is required")


def _validate_page_selection(page: dict[str, Any], page_no: int) -> None:
    page_type = _require_string(page["page_type"], f"page {page_no} page_type")
    layout_type = _require_string(page["layout_type"], f"page {page_no} layout_type")
    validate_page_type(page_type)
    validate_layout_type(layout_type)
    if page_type == "unknown" or layout_type == "unknown":
        raise ValueError(f"page {page_no} classification is unresolved")
    if type(page["index_eligible"]) is not bool or page["index_eligible"] != is_index_eligible(page_type):
        raise ValueError(f"page {page_no} index eligibility mismatch")
    if page["selected_engine"] not in _SELECTED_ENGINES:
        raise ValueError(f"page {page_no} selected engine is invalid")
    if page["selected_engine"] == "codex" and not str(page["corrected_text"] or "").strip():
        raise ValueError(f"page {page_no} Codex correction is empty")
    if page["selected_engine"] != "codex" and str(page["corrected_text"] or "").strip():
        raise ValueError(f"page {page_no} unused Codex correction is present")
    _require_string(page["selection_reason"], f"page {page_no} selection_reason")
    if page_type == "narrative" and not _selected_text(page).strip():
        raise ValueError(f"page {page_no} selected narrative text is empty")


def _validate_page(page: Any, expected_page_no: int) -> dict[str, Any]:
    if not isinstance(page, dict):
        raise ValueError(f"page {expected_page_no} must be an object")
    _require_exact_keys(page, _PAGE_KEYS, f"page {expected_page_no}")
    if type(page["page_no"]) is not int or page["page_no"] != expected_page_no:
        raise ValueError(f"package pages must be contiguous from 1: expected {expected_page_no}")
    _validate_page_result(page, expected_page_no)
    _validate_page_review(page, expected_page_no)
    _validate_page_selection(page, expected_page_no)
    _validate_raw_envelope(page)
    return page


def _validate_fingerprint_consistency(pages: list[dict[str, Any]]) -> None:
    fingerprints: dict[str, set[str]] = {"primary": set(), "external": set()}
    for page in pages:
        envelope = json.loads(str(page["raw_output"]))
        for candidate in fingerprints:
            fingerprints[candidate].add(str(envelope[candidate]["provenance"]["model_fingerprint"]))
    mixed = [candidate for candidate, values in fingerprints.items() if len(values) != 1]
    if mixed:
        raise ValueError(f"reviewed OCR package mixes model fingerprints: {mixed}")


def _validate_package_metadata(package: dict[str, Any]) -> None:
    _require_exact_keys(package, _PACKAGE_KEYS, "reviewed OCR package")
    if package["schema_version"] != PACKAGE_SCHEMA_VERSION:
        raise ValueError("unsupported reviewed OCR package schema")
    package_sha256 = _validate_sha256(package["package_sha256"], "package_sha256")
    if _package_digest(package) != package_sha256:
        raise ValueError("reviewed OCR package digest mismatch")
    if type(package["source_run_id"]) is not int or package["source_run_id"] <= 0:
        raise ValueError("source_run_id must be a positive integer")
    book_name = _require_string(package["book_name"], "book_name")
    validate_safe_name(book_name, param_name="book_name")
    if package["engine"] != _SOURCE_ENGINE or package["model"] != COMPOSITE_MODEL_REVISION:
        raise ValueError("reviewed OCR package engine or model revision mismatch")
    if type(package["source_page_count"]) is not int or package["source_page_count"] <= 0:
        raise ValueError("source_page_count must be a positive integer")
    review = package["review"]
    if not isinstance(review, dict) or set(review) != {"actor", "note"}:
        raise ValueError("review metadata fields mismatch")
    actor = _require_string(review["actor"], "review actor")
    if actor.casefold() != "codex":
        raise ValueError("review actor must be codex")
    _require_string(review["note"], "review note")


def validate_reviewed_package(package: Any) -> dict[str, Any]:
    if not isinstance(package, dict):
        raise ValueError("reviewed OCR package must be an object")
    _validate_package_metadata(package)
    pages = package["pages"]
    if not isinstance(pages, list) or len(pages) != package["source_page_count"]:
        raise ValueError("reviewed OCR package page count mismatch")
    for page_no, page in enumerate(pages, start=1):
        _validate_page(page, page_no)
    _validate_fingerprint_consistency(pages)
    return package


def export_reviewed_run(
    *,
    db_path: Path,
    run_id: int,
    reviewer: str,
    review_note: str,
) -> dict[str, Any]:
    _require_string(reviewer, "reviewer")
    _require_string(review_note, "review_note")
    with open_db(str(db_path)) as conn:
        run = conn.execute(
            "SELECT book_name, engine, model, source_page_count, state FROM ocr_runs WHERE id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise LookupError(f"OCR run not found: {run_id}")
        if run[1] != _SOURCE_ENGINE or run[2] != COMPOSITE_MODEL_REVISION:
            raise ValueError("only the fixed Qwen+dots review run can be exported")
        if run[4] not in {"awaiting_qa", "completed"}:
            raise ValueError("OCR run is not review-complete")
        rows = conn.execute(
            "SELECT page_no, image_sha256, state, full_text, char_count, raw_output, block_count, "
            "quality_flags_json, ink_coverage, attempt_count, error_message, qa_state, qa_note, reviewed_at, "
            "page_type, index_eligible, layout_type, primary_text, external_text, selected_engine, "
            "corrected_text, selection_reason FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (run_id,),
        ).fetchall()
    pages: list[dict[str, Any]] = []
    for row in rows:
        try:
            quality_flags = json.loads(str(row[7]))
        except json.JSONDecodeError as exc:
            raise ValueError(f"page {int(row[0])} quality flags are not JSON") from exc
        qa_state = str(row[11])
        qa_note = row[12]
        if qa_state == "approved" and not str(qa_note or "").strip():
            qa_note = f"owner image review accepted; legacy QA note unavailable; package attestation: {review_note}"
        pages.append(
            {
                "page_no": int(row[0]),
                "image_sha256": str(row[1]),
                "state": str(row[2]),
                "full_text": str(row[3] or ""),
                "char_count": int(row[4]),
                "raw_output": str(row[5] or ""),
                "block_count": int(row[6]),
                "quality_flags": quality_flags,
                "ink_coverage": row[8],
                "attempt_count": int(row[9]),
                "error_message": row[10],
                "qa_state": qa_state,
                "qa_note": qa_note,
                "reviewed_at": row[13],
                "review_method": _review_method(qa_state, qa_note),
                "page_type": str(row[14]),
                "index_eligible": bool(row[15]),
                "layout_type": str(row[16]),
                "primary_text": row[17],
                "external_text": row[18],
                "selected_engine": str(row[19]),
                "corrected_text": row[20],
                "selection_reason": row[21],
            }
        )
    package: dict[str, Any] = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_sha256": "",
        "source_run_id": run_id,
        "book_name": str(run[0]),
        "source_page_count": int(run[3]),
        "engine": str(run[1]),
        "model": str(run[2]),
        "review": {"actor": reviewer, "note": review_note},
        "pages": pages,
    }
    package["package_sha256"] = _package_digest(package)
    return validate_reviewed_package(package)


def write_reviewed_package(path: Path, package: dict[str, Any]) -> None:
    validate_reviewed_package(package)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_reviewed_package(path: Path) -> dict[str, Any]:
    try:
        package = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("reviewed OCR package is not valid JSON") from exc
    return validate_reviewed_package(package)
