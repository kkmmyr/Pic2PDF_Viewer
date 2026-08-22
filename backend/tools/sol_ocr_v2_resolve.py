"""Bind Sol OCR v2 A/B candidates to third-session checker decisions."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from services.novel_db.sol_ocr_campaign import (
    build_checker_v2_artifact,
    build_resolved_v2_artifact,
    load_page_candidate_v2_artifact,
    load_pilot_manifest,
    validate_resolved_v2_artifact,
)


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _write_idempotent(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        if _load_object(path) != value:
            raise ValueError(f"conflicting Sol OCR v2 resolved artifact: {path.name}")
        return
    _atomic_write_json(path, value)


def resolve_candidates(
    *,
    candidate_a_dir: Path,
    candidate_b_dir: Path,
    checker_raw_dir: Path,
    selection_manifest_path: Path,
    pilot_manifest_path: Path,
    images_root: Path,
    checker_output_dir: Path,
    resolved_output_dir: Path,
) -> dict[str, Any]:
    selection = _load_object(selection_manifest_path)
    expected_ids = {str(sample["sample_id"]) for sample in selection.get("samples", [])}
    if not expected_ids:
        raise ValueError("selection manifest has no samples")
    pilot = load_pilot_manifest(pilot_manifest_path)
    checker_files = {path.name.split(".")[0]: path for path in checker_raw_dir.glob("pilot-*.json")}
    if set(checker_files) != expected_ids:
        raise ValueError(
            "raw checker sample set mismatch: "
            f"missing={sorted(expected_ids - set(checker_files))}, extra={sorted(set(checker_files) - expected_ids)}"
        )

    passes = 0
    needs_review = 0
    for sample_id in sorted(expected_ids):
        candidate_a = load_page_candidate_v2_artifact(candidate_a_dir / f"{sample_id}.candidate-a.v2.json")
        candidate_b = load_page_candidate_v2_artifact(candidate_b_dir / f"{sample_id}.candidate-b.v2.json")
        checker = build_checker_v2_artifact(
            _load_object(checker_files[sample_id]),
            candidate_a=candidate_a,
            candidate_b=candidate_b,
        )
        canonical_eligible = (
            checker["verdict"] == "pass"
            and checker["selection"] in {"a", "b"}
            and checker["candidate_coverage"][checker["selection"]] == "complete"
            and checker["reading_order"] == "pass"
            and not checker["major_errors"]
        )
        resolved = build_resolved_v2_artifact(
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            checker=checker,
            canonical_eligible=canonical_eligible,
            resolved_at=str(checker["checked_at"]),
        )
        validate_resolved_v2_artifact(
            resolved,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            checker=checker,
            pilot_manifest=pilot,
            images_root=images_root,
        )
        _write_idempotent(checker_output_dir / f"{sample_id}.checker.v2.json", checker)
        _write_idempotent(resolved_output_dir / f"{sample_id}.resolved.v2.json", resolved)
        if canonical_eligible:
            passes += 1
        else:
            needs_review += 1
    return {"sample_count": len(expected_ids), "canonical_eligible": passes, "needs_review": needs_review}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-a-dir", type=Path, required=True)
    parser.add_argument("--candidate-b-dir", type=Path, required=True)
    parser.add_argument("--checker-raw-dir", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--checker-output-dir", type=Path, required=True)
    parser.add_argument("--resolved-output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            resolve_candidates(
                candidate_a_dir=args.candidate_a_dir,
                candidate_b_dir=args.candidate_b_dir,
                checker_raw_dir=args.checker_raw_dir,
                selection_manifest_path=args.selection,
                pilot_manifest_path=args.pilot,
                images_root=args.images_root,
                checker_output_dir=args.checker_output_dir,
                resolved_output_dir=args.resolved_output_dir,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
