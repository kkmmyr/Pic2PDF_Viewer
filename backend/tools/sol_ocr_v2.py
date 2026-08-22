"""Normalize and validate Sol image-OCR v2 worker artifacts."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from services.novel_db.sol_ocr_campaign import (
    build_page_candidate_v2_artifact,
    load_pilot_manifest,
    validate_page_candidate_v2_artifact,
)


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


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def normalize_candidates(
    *,
    raw_dir: Path,
    selection_manifest_path: Path,
    pilot_manifest_path: Path,
    images_root: Path,
    purpose: str,
    output_dir: Path,
) -> dict[str, Any]:
    selection = _load_object(selection_manifest_path)
    expected_ids = {str(sample["sample_id"]) for sample in selection.get("samples", [])}
    if not expected_ids:
        raise ValueError("selection manifest has no samples")
    pilot = load_pilot_manifest(pilot_manifest_path)
    artifacts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_path in sorted(raw_dir.glob("pilot-*.json")):
        if "strip" in raw_path.name:
            continue
        artifact = build_page_candidate_v2_artifact(
            _load_object(raw_path),
            pilot_manifest=pilot,
            purpose=purpose,
        )
        validate_page_candidate_v2_artifact(artifact, pilot_manifest=pilot, images_root=images_root)
        sample_id = str(artifact["sample_id"])
        if sample_id in seen_ids:
            raise ValueError(f"duplicate raw candidate: {sample_id}")
        seen_ids.add(sample_id)
        artifacts.append(artifact)
    if seen_ids != expected_ids:
        raise ValueError(
            "raw candidate sample set mismatch: "
            f"missing={sorted(expected_ids - seen_ids)}, extra={sorted(seen_ids - expected_ids)}"
        )
    candidate_ids = {str(artifact["candidate_id"]) for artifact in artifacts}
    if len(candidate_ids) != 1:
        raise ValueError(f"raw directory mixes candidate IDs: {sorted(candidate_ids)}")
    candidate_id = candidate_ids.pop()
    for artifact in artifacts:
        output_path = output_dir / f"{artifact['sample_id']}.candidate-{candidate_id}.v2.json"
        if output_path.exists():
            existing = _load_object(output_path)
            if existing != artifact:
                raise ValueError(f"conflicting normalized candidate: {artifact['sample_id']}")
            continue
        _atomic_write_json(output_path, artifact)
    return {"candidate_id": candidate_id, "artifact_count": len(artifacts), "sample_ids": sorted(seen_ids)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--images-root", type=Path, required=True)
    parser.add_argument("--purpose", choices=("tuning", "formal"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            normalize_candidates(
                raw_dir=args.raw_dir,
                selection_manifest_path=args.selection,
                pilot_manifest_path=args.pilot,
                images_root=args.images_root,
                purpose=args.purpose,
                output_dir=args.output_dir,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
