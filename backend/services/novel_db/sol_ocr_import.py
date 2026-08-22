"""Validated Sol image-OCR artifact import and legacy comparison reporting."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .connection import open_db
from .ocr_ground_truth import character_error_rate
from .sol_ocr_campaign import (
    SOL_MODEL,
    SOL_PROMPT_VERSION,
    load_checker_v2_artifact,
    load_page_artifact,
    load_page_candidate_v2_artifact,
    load_resolved_v2_artifact,
    validate_page_artifact,
    validate_resolved_v2_artifact,
)


def _model_revision(
    *,
    manifest_sha256: str,
    pilot_sha256: str,
    prompt_version: str = SOL_PROMPT_VERSION,
    prompt_sha256: str | None = None,
    policy_sha256: str | None = None,
    purpose: str | None = None,
) -> str:
    """Keep runs from different immutable inputs out of the same checkpoint."""
    revision = f"{SOL_MODEL}/{prompt_version}/{manifest_sha256[:16]}/{pilot_sha256[:16]}"
    if prompt_sha256 is None and policy_sha256 is None and purpose is None:
        return revision
    if not prompt_sha256 or not policy_sha256 or not purpose:
        raise ValueError("Sol OCR v2 model revision requires prompt, policy, and purpose hashes")
    return f"{revision}/{prompt_sha256[:16]}/{policy_sha256[:16]}/{purpose}"


def _legacy_text(conn: sqlite3.Connection, book_name: str, page_no: int) -> str | None:
    row = conn.execute(
        "SELECT pr.published_text FROM books b "
        "JOIN ocr_publications op ON op.book_id=b.id AND op.retired_at IS NULL "
        "JOIN ocr_runs r ON r.id=op.run_id AND r.engine='legacy' "
        "JOIN ocr_page_results pr ON pr.run_id=r.id AND pr.page_no=? WHERE b.name=?",
        (page_no, book_name),
    ).fetchone()
    return None if row is None else str(row[0] or "")


def _get_or_create_run(
    conn: sqlite3.Connection,
    *,
    book_name: str,
    source_page_count: int,
    model_revision: str,
) -> int:
    row = conn.execute(
        "SELECT id FROM ocr_runs WHERE book_name=? AND engine='sol' AND model=? "
        "AND source_page_count=? AND state IN ('running', 'failed') ORDER BY id DESC LIMIT 1",
        (book_name, model_revision, source_page_count),
    ).fetchone()
    if row is not None:
        run_id = int(row[0])
        conn.execute(
            "UPDATE ocr_runs SET state='running', finished_at=NULL, error_message=NULL WHERE id=?",
            (run_id,),
        )
        return run_id
    cursor = conn.execute(
        "INSERT INTO ocr_runs "
        "(book_name, engine, model, source_page_count, state, started_at, qa_state) "
        "VALUES (?, 'sol', ?, ?, 'running', datetime('now', '+9 hours'), 'pending')",
        (book_name, model_revision, source_page_count),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("failed to create Sol OCR run")
    return int(cursor.lastrowid)


def import_pilot_artifacts(
    *,
    db_path: Path,
    campaign_manifest: dict[str, Any],
    pilot_manifest: dict[str, Any],
    images_root: Path,
    artifact_paths: list[Path],
) -> dict[str, Any]:
    """Validate every artifact first, then import the complete batch atomically."""
    validated: list[dict[str, Any]] = []
    seen_samples: set[str] = set()
    for artifact_path in sorted(artifact_paths):
        artifact = load_page_artifact(artifact_path)
        validate_page_artifact(artifact, pilot_manifest=pilot_manifest, images_root=images_root)
        sample_id = str(artifact["sample_id"])
        if sample_id in seen_samples:
            raise ValueError(f"duplicate Sol OCR artifact: {sample_id}")
        seen_samples.add(sample_id)
        validated.append(artifact)

    expected_samples = {str(sample["sample_id"]) for sample in pilot_manifest["samples"]}
    if seen_samples != expected_samples:
        missing = sorted(expected_samples - seen_samples)
        extra = sorted(seen_samples - expected_samples)
        raise ValueError(f"Sol OCR artifact sample set mismatch: missing={missing}, extra={extra}")

    campaign_books = {str(book["book_name"]): book for book in campaign_manifest["books"]}
    model_revision = _model_revision(
        manifest_sha256=str(pilot_manifest["manifest_sha256"]),
        pilot_sha256=str(pilot_manifest["pilot_sha256"]),
    )
    inserted = 0
    idempotent = 0
    run_ids: set[int] = set()
    with open_db(str(db_path)) as conn, conn:
        for artifact in validated:
            book_name = str(artifact["book_name"])
            campaign_book = campaign_books.get(book_name)
            if campaign_book is None:
                raise ValueError(f"Sol OCR artifact book is outside campaign: {book_name}")
            run_id = _get_or_create_run(
                conn,
                book_name=book_name,
                source_page_count=int(campaign_book["page_count"]),
                model_revision=model_revision,
            )
            run_ids.add(run_id)
            existing = conn.execute(
                "SELECT image_sha256, primary_text, raw_output FROM ocr_page_results WHERE run_id=? AND page_no=?",
                (run_id, int(artifact["page_no"])),
            ).fetchone()
            raw_output = json.dumps(artifact, ensure_ascii=False, sort_keys=True)
            if existing is not None:
                if (str(existing[0]), str(existing[1] or ""), str(existing[2] or "")) != (
                    str(artifact["image_sha256"]),
                    str(artifact["text"]),
                    raw_output,
                ):
                    raise ValueError(f"conflicting Sol OCR artifact: {artifact['sample_id']}")
                idempotent += 1
                continue
            text = str(artifact["text"])
            notes = list(artifact["transcription_notes"])
            flags = ["sol_image_ocr_pilot"]
            if notes:
                flags.append("sol_transcription_note")
            conn.execute(
                "INSERT INTO ocr_page_results "
                "(run_id, page_no, image_sha256, state, full_text, char_count, raw_output, block_count, "
                "quality_flags_json, attempt_count, qa_state, page_type, layout_type, primary_text, "
                "external_text, selected_engine, published_text, index_eligible, updated_at) "
                "VALUES (?, ?, ?, 'passed', ?, ?, ?, ?, ?, 1, 'not_required', 'unknown', 'unknown', ?, ?, "
                "'primary', NULL, 0, datetime('now', '+9 hours'))",
                (
                    run_id,
                    int(artifact["page_no"]),
                    str(artifact["image_sha256"]),
                    text,
                    len(text),
                    raw_output,
                    len([line for line in text.splitlines() if line.strip()]),
                    json.dumps(flags, ensure_ascii=False),
                    text,
                    _legacy_text(conn, book_name, int(artifact["page_no"])),
                ),
            )
            inserted += 1
    return {
        "artifact_count": len(validated),
        "inserted": inserted,
        "idempotent": idempotent,
        "run_count": len(run_ids),
        "run_ids": sorted(run_ids),
    }


ResolvedV2Bundle = tuple[Path, Path, Path, Path]


def _resolved_v2_raw_envelope(
    *,
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
    checker: dict[str, Any],
    resolved: dict[str, Any],
) -> str:
    """Persist every signed v2 artifact, rather than only its selected text."""
    envelope = {
        "schema_version": "sol-ocr-import-v2-envelope-v1",
        "candidate_a": candidate_a,
        "candidate_b": candidate_b,
        "checker": checker,
        "resolved": resolved,
        "sha256": {
            "candidate_a": candidate_a["candidate_sha256"],
            "candidate_b": candidate_b["candidate_sha256"],
            "checker": checker["checker_sha256"],
            "resolved": resolved["resolved_sha256"],
        },
    }
    return json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _expected_v2_sample_ids(
    *,
    pilot_manifest: dict[str, Any],
    expected_samples: list[dict[str, Any]] | None,
) -> set[str]:
    pilot_samples = {str(sample["sample_id"]): sample for sample in pilot_manifest["samples"]}
    selected = pilot_manifest["samples"] if expected_samples is None else expected_samples
    expected_ids: set[str] = set()
    for sample in selected:
        if not isinstance(sample, dict) or not isinstance(sample.get("sample_id"), str):
            raise ValueError("Sol OCR v2 expected sample must contain sample_id")
        sample_id = sample["sample_id"]
        pilot_sample = pilot_samples.get(sample_id)
        if pilot_sample is None:
            raise ValueError(f"Sol OCR v2 expected sample is outside pilot manifest: {sample_id}")
        for field in ("book_name", "page_no", "image_sha256"):
            if field in sample and sample[field] != pilot_sample[field]:
                raise ValueError(f"Sol OCR v2 expected sample {field} mismatch: {sample_id}")
        if sample_id in expected_ids:
            raise ValueError(f"duplicate Sol OCR v2 expected sample: {sample_id}")
        expected_ids.add(sample_id)
    return expected_ids


def import_resolved_v2_bundles(
    *,
    db_path: Path,
    campaign_manifest: dict[str, Any],
    pilot_manifest: dict[str, Any],
    images_root: Path,
    bundle_paths: list[ResolvedV2Bundle],
    expected_samples: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Atomically stage a complete set of independently resolved v2 OCR bundles.

    Each path tuple is ordered as candidate A, candidate B, checker, resolved.
    No database connection is opened until every artifact and the exact expected
    sample set have passed validation.
    """
    validated: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    seen_samples: set[str] = set()
    for candidate_a_path, candidate_b_path, checker_path, resolved_path in sorted(bundle_paths):
        candidate_a = load_page_candidate_v2_artifact(candidate_a_path)
        candidate_b = load_page_candidate_v2_artifact(candidate_b_path)
        checker = load_checker_v2_artifact(checker_path)
        resolved = load_resolved_v2_artifact(resolved_path)
        sample = validate_resolved_v2_artifact(
            resolved,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            checker=checker,
            pilot_manifest=pilot_manifest,
            images_root=images_root,
        )
        sample_id = str(sample["sample_id"])
        if sample_id in seen_samples:
            raise ValueError(f"duplicate Sol OCR v2 bundle: {sample_id}")
        seen_samples.add(sample_id)
        validated.append((candidate_a, candidate_b, checker, resolved, sample))

    expected_ids = _expected_v2_sample_ids(pilot_manifest=pilot_manifest, expected_samples=expected_samples)
    if seen_samples != expected_ids:
        missing = sorted(expected_ids - seen_samples)
        extra = sorted(seen_samples - expected_ids)
        raise ValueError(f"Sol OCR v2 bundle sample set mismatch: missing={missing}, extra={extra}")

    campaign_books = {str(book["book_name"]): book for book in campaign_manifest["books"]}
    inserted = 0
    idempotent = 0
    run_ids: set[int] = set()
    with open_db(str(db_path)) as conn, conn:
        for candidate_a, candidate_b, checker, resolved, sample in validated:
            book_name = str(sample["book_name"])
            campaign_book = campaign_books.get(book_name)
            if campaign_book is None:
                raise ValueError(f"Sol OCR v2 bundle book is outside campaign: {book_name}")
            model_revision = _model_revision(
                manifest_sha256=str(resolved["manifest_sha256"]),
                pilot_sha256=str(resolved["pilot_sha256"]),
                prompt_sha256=str(resolved["prompt_sha256"]),
                policy_sha256=str(resolved["policy_sha256"]),
                purpose=str(resolved["purpose"]),
            )
            run_id = _get_or_create_run(
                conn,
                book_name=book_name,
                source_page_count=int(campaign_book["page_count"]),
                model_revision=model_revision,
            )
            run_ids.add(run_id)
            raw_output = _resolved_v2_raw_envelope(
                candidate_a=candidate_a,
                candidate_b=candidate_b,
                checker=checker,
                resolved=resolved,
            )
            existing = conn.execute(
                "SELECT image_sha256, raw_output FROM ocr_page_results WHERE run_id=? AND page_no=?",
                (run_id, int(sample["page_no"])),
            ).fetchone()
            if existing is not None:
                if (str(existing[0]), str(existing[1] or "")) != (str(sample["image_sha256"]), raw_output):
                    raise ValueError(f"conflicting Sol OCR v2 envelope: {sample['sample_id']}")
                idempotent += 1
                continue

            selection = checker["selection"]
            canonical_eligible = bool(resolved["canonical_eligible"])
            is_resolved = canonical_eligible and checker["verdict"] == "pass" and selection in {"a", "b"}
            is_publishable = is_resolved and resolved["purpose"] == "formal"
            selected_text = (
                candidate_a["text"] if selection == "a" else candidate_b["text"] if selection == "b" else None
            )
            flags = [
                "sol_image_ocr_v2",
                f"sol_ocr_v2_purpose:{resolved['purpose']}",
                f"sol_ocr_v2_verdict:{checker['verdict']}",
            ]
            if resolved["purpose"] == "tuning":
                flags.append("sol_ocr_v2_tuning_not_publishable")
            if not is_resolved:
                flags.append("sol_ocr_v2_needs_review")
            if checker["major_errors"]:
                flags.append("sol_ocr_v2_checker_major_errors")

            conn.execute(
                "INSERT INTO ocr_page_results "
                "(run_id, page_no, image_sha256, state, full_text, char_count, raw_output, block_count, "
                "quality_flags_json, attempt_count, qa_state, qa_note, page_type, layout_type, primary_text, "
                "external_text, selected_engine, published_text, index_eligible, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'unknown', 'unknown', ?, ?, ?, NULL, 0, "
                "datetime('now', '+9 hours'))",
                (
                    run_id,
                    int(sample["page_no"]),
                    str(sample["image_sha256"]),
                    "passed" if is_publishable else "needs_review",
                    selected_text if is_resolved else None,
                    len(selected_text or "") if is_resolved else 0,
                    raw_output,
                    len([line for line in (selected_text or "").splitlines() if line.strip()]) if is_resolved else 0,
                    json.dumps(flags, ensure_ascii=False),
                    "not_required" if is_publishable else "pending",
                    None
                    if is_publishable
                    else "tuning artifacts are not publishable"
                    if is_resolved
                    else str(checker["reason"]),
                    str(candidate_a["text"]),
                    str(candidate_b["text"]),
                    "primary"
                    if selection == "a" and is_resolved
                    else "external"
                    if selection == "b" and is_resolved
                    else "unresolved",
                ),
            )
            inserted += 1
    return {
        "bundle_count": len(validated),
        "inserted": inserted,
        "idempotent": idempotent,
        "run_count": len(run_ids),
        "run_ids": sorted(run_ids),
    }


def build_pilot_comparison_report(*, db_path: Path, pilot_manifest: dict[str, Any]) -> dict[str, Any]:
    """Compare Sol to legacy without treating legacy as ground truth."""
    pages: list[dict[str, Any]] = []
    total_distance = 0
    total_legacy_chars = 0
    canonical_compared = 0
    model_revision = _model_revision(
        manifest_sha256=str(pilot_manifest["manifest_sha256"]),
        pilot_sha256=str(pilot_manifest["pilot_sha256"]),
    )
    with open_db(str(db_path)) as conn:
        for sample in pilot_manifest["samples"]:
            row = conn.execute(
                "SELECT pr.primary_text, pr.external_text FROM ocr_runs r "
                "JOIN ocr_page_results pr ON pr.run_id=r.id "
                "WHERE r.book_name=? AND r.engine='sol' AND r.model=? AND pr.page_no=? "
                "ORDER BY r.id DESC LIMIT 1",
                (
                    str(sample["book_name"]),
                    model_revision,
                    int(sample["page_no"]),
                ),
            ).fetchone()
            if row is None:
                pages.append({"sample_id": sample["sample_id"], "state": "missing"})
                continue
            sol_text = str(row[0] or "")
            legacy_text = None if row[1] is None else str(row[1])
            page_report: dict[str, Any] = {
                "sample_id": sample["sample_id"],
                "group": sample["group"],
                "book_name": sample["book_name"],
                "page_no": sample["page_no"],
                "state": "imported",
                "sol_chars": len(sol_text),
                "legacy_chars": None if legacy_text is None else len(legacy_text),
                "char_delta": None if legacy_text is None else len(sol_text) - len(legacy_text),
                "normalized_edit_distance_vs_legacy": None,
                "normalized_edit_rate_vs_legacy": None,
            }
            if legacy_text is not None:
                distance, legacy_chars, edit_rate = character_error_rate(legacy_text, sol_text)
                page_report["normalized_edit_distance_vs_legacy"] = distance
                page_report["normalized_edit_rate_vs_legacy"] = edit_rate
                total_distance += distance
                total_legacy_chars += legacy_chars
                canonical_compared += 1
            pages.append(page_report)
    imported = sum(page.get("state") == "imported" for page in pages)
    return {
        "schema_version": "sol-ocr-pilot-comparison-v1",
        "campaign_id": pilot_manifest["campaign_id"],
        "pilot_sha256": pilot_manifest["pilot_sha256"],
        "summary": {
            "sample_count": len(pages),
            "imported": imported,
            "missing": len(pages) - imported,
            "canonical_compared": canonical_compared,
            "normalized_edit_distance_vs_legacy": total_distance,
            "normalized_legacy_chars": total_legacy_chars,
            "normalized_edit_rate_vs_legacy": total_distance / total_legacy_chars if total_legacy_chars else None,
            "warning": "legacy is not verified ground truth; this edit rate is not CER or accuracy",
        },
        "pages": pages,
    }


def build_pilot_review_package(*, db_path: Path, pilot_manifest: dict[str, Any]) -> dict[str, Any]:
    """Build a local-only image/Sol/legacy package for visual adjudication."""
    samples_by_id = {str(sample["sample_id"]): sample for sample in pilot_manifest["samples"]}
    comparison = build_pilot_comparison_report(db_path=db_path, pilot_manifest=pilot_manifest)
    model_revision = _model_revision(
        manifest_sha256=str(pilot_manifest["manifest_sha256"]),
        pilot_sha256=str(pilot_manifest["pilot_sha256"]),
    )
    pages: list[dict[str, Any]] = []
    with open_db(str(db_path)) as conn:
        for metric in comparison["pages"]:
            sample = samples_by_id[str(metric["sample_id"])]
            row = conn.execute(
                "SELECT pr.primary_text, pr.external_text FROM ocr_runs r "
                "JOIN ocr_page_results pr ON pr.run_id=r.id "
                "WHERE r.book_name=? AND r.engine='sol' AND r.model=? AND pr.page_no=? "
                "ORDER BY r.id DESC LIMIT 1",
                (
                    str(sample["book_name"]),
                    model_revision,
                    int(sample["page_no"]),
                ),
            ).fetchone()
            pages.append(
                {
                    **metric,
                    "image_path": sample["image_path"],
                    "image_sha256": sample["image_sha256"],
                    "sol_text": None if row is None else str(row[0] or ""),
                    "legacy_text": None if row is None or row[1] is None else str(row[1]),
                }
            )
    return {
        "schema_version": "sol-ocr-pilot-review-v1",
        "campaign_id": pilot_manifest["campaign_id"],
        "pilot_sha256": pilot_manifest["pilot_sha256"],
        "warning": "local-only copyrighted text; do not commit or share externally",
        "pages": pages,
    }
