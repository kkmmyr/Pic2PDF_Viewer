#!/usr/bin/env python3
"""Audit and deduplicate a private PARSeq line-crop training manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image


class ManifestAuditError(RuntimeError):
    """Raised when the private training corpus fails a safety invariant."""


@dataclass(frozen=True)
class SampleRecord:
    index: int
    run_id: int
    page_no: int
    segment_index: int
    image_path: str
    image_sha256: str
    width: int
    height: int
    label_chars: int
    label: str

    @property
    def key(self) -> tuple[int, int, int]:
        return self.run_id, self.page_no, self.segment_index


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_sample(
    indexed_sample: tuple[int, dict[str, Any]],
    *,
    images_dir: Path,
    labels_dir: Path,
) -> SampleRecord:
    index, sample = indexed_sample
    image_path = Path(str(sample["image"])).resolve()
    if image_path.parent != images_dir.resolve() or not image_path.is_file():
        raise ManifestAuditError(
            f"sample image is missing or outside corpus: {image_path}"
        )
    label_path = labels_dir.resolve() / f"{image_path.stem}.txt"
    if not label_path.is_file():
        raise ManifestAuditError(f"sample label file is missing: {label_path}")
    label = str(sample["label"])
    if label_path.read_text(encoding="utf-8") != label:
        raise ManifestAuditError(f"sample label file differs: {label_path}")
    label_chars = int(sample["label_chars"])
    if label_chars != len(label) or not 5 <= label_chars <= 100:
        raise ManifestAuditError(
            f"sample label length is invalid: {image_path.name}: "
            f"stored={label_chars}, actual={len(label)}"
        )
    with Image.open(image_path) as image:
        width, height = image.size
        image.verify()
    if width <= 0 or height <= 0 or width < height:
        raise ManifestAuditError(
            f"sample dimensions are invalid: {image_path.name}: {width}x{height}"
        )
    return SampleRecord(
        index=index,
        run_id=int(sample["run_id"]),
        page_no=int(sample["page_no"]),
        segment_index=int(sample["segment_index"]),
        image_path=str(image_path),
        image_sha256=sha256_file(image_path),
        width=width,
        height=height,
        label_chars=label_chars,
        label=label,
    )


def deduplicate_records(
    records: list[SampleRecord], *, excluded_conflict_hashes: set[str]
) -> tuple[list[SampleRecord], dict[str, Any]]:
    by_key: dict[tuple[int, int, int], SampleRecord] = {}
    by_hash: dict[str, list[SampleRecord]] = defaultdict(list)
    for record in records:
        if record.key in by_key:
            raise ManifestAuditError(f"duplicate run/page/segment key: {record.key}")
        by_key[record.key] = record
        by_hash[record.image_sha256].append(record)

    conflict_hashes = {
        image_hash
        for image_hash, group in by_hash.items()
        if len({record.label for record in group}) > 1
    }
    unknown_exclusions = excluded_conflict_hashes - conflict_hashes
    unresolved_conflicts = conflict_hashes - excluded_conflict_hashes
    if unknown_exclusions:
        raise ManifestAuditError(
            f"explicit conflict exclusions are not conflicts: {sorted(unknown_exclusions)}"
        )
    if unresolved_conflicts:
        raise ManifestAuditError(
            f"conflicting image labels require review: {sorted(unresolved_conflicts)}"
        )

    retained: list[SampleRecord] = []
    same_label_duplicate_groups = 0
    same_label_duplicate_samples = 0
    excluded_conflict_samples = 0
    for image_hash, group in sorted(by_hash.items()):
        ordered = sorted(group, key=lambda record: (record.key, record.image_path))
        if image_hash in excluded_conflict_hashes:
            excluded_conflict_samples += len(ordered)
            continue
        retained.append(ordered[0])
        if len(ordered) > 1:
            same_label_duplicate_groups += 1
            same_label_duplicate_samples += len(ordered) - 1
    retained.sort(key=lambda record: (record.key, record.image_path))
    return retained, {
        "input_samples": len(records),
        "retained_samples": len(retained),
        "same_label_duplicate_groups": same_label_duplicate_groups,
        "same_label_duplicate_samples_removed": same_label_duplicate_samples,
        "conflicting_hashes_excluded": sorted(excluded_conflict_hashes),
        "conflicting_samples_removed": excluded_conflict_samples,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--validation-run-id", type=int, action="append", required=True)
    parser.add_argument("--forbidden-run-id", type=int, action="append", default=[])
    parser.add_argument("--exclude-conflict-sha", action="append", default=[])
    parser.add_argument("--max-workers", type=int, default=16)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    output_manifest = args.output_manifest.resolve()
    audit_output = args.audit_output.resolve()
    if output_manifest == manifest_path:
        raise ManifestAuditError(
            "output manifest must not overwrite the source manifest"
        )
    if output_manifest.exists() or audit_output.exists():
        raise ManifestAuditError("audit outputs already exist")
    if args.max_workers <= 0:
        raise ManifestAuditError("max-workers must be positive")
    validation_runs = set(args.validation_run_id)
    forbidden_runs = set(args.forbidden_run_id)
    if validation_runs & forbidden_runs:
        raise ManifestAuditError("validation and forbidden runs overlap")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = payload.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ManifestAuditError("source manifest contains no samples")
    corpus_root = manifest_path.parent
    images_dir = corpus_root / "images"
    labels_dir = corpus_root / "labels"
    indexed = list(enumerate(samples))
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        records = []
        for count, record in enumerate(
            executor.map(
                lambda item: inspect_sample(
                    item, images_dir=images_dir, labels_dir=labels_dir
                ),
                indexed,
            ),
            start=1,
        ):
            records.append(record)
            if count % 10000 == 0:
                print(f"audited_samples={count}", flush=True)

    present_runs = {record.run_id for record in records}
    forbidden_present = present_runs & forbidden_runs
    if forbidden_present:
        raise ManifestAuditError(
            f"manifest contains final holdout runs: {sorted(forbidden_present)}"
        )
    missing_validation = validation_runs - present_runs
    if missing_validation:
        raise ManifestAuditError(
            f"validation runs contain no samples: {sorted(missing_validation)}"
        )
    excluded_hashes = {value.lower() for value in args.exclude_conflict_sha}
    retained, duplicate_report = deduplicate_records(
        records, excluded_conflict_hashes=excluded_hashes
    )
    validation = [record for record in retained if record.run_id in validation_runs]
    training = [record for record in retained if record.run_id not in validation_runs]
    if not training or not validation:
        raise ManifestAuditError("training or validation split is empty")
    if {record.run_id for record in training} & {
        record.run_id for record in validation
    }:
        raise ManifestAuditError("training and validation run IDs overlap")
    train_hashes = {record.image_sha256 for record in training}
    validation_hashes = {record.image_sha256 for record in validation}
    if train_hashes & validation_hashes:
        raise ManifestAuditError("training and validation image hashes overlap")

    retained_samples = [samples[record.index] for record in retained]
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(
        json.dumps(
            {
                "created_at": datetime.now(UTC).isoformat(),
                "source_manifest_sha256": sha256_file(manifest_path),
                "samples": retained_samples,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    split_counts = {
        "training": {
            "run_ids": sorted({record.run_id for record in training}),
            "samples": len(training),
            "label_chars": sum(record.label_chars for record in training),
        },
        "validation": {
            "run_ids": sorted(validation_runs),
            "samples": len(validation),
            "label_chars": sum(record.label_chars for record in validation),
        },
    }
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "contains_labels": False,
        "contains_images": False,
        "source_manifest": {
            "sha256": sha256_file(manifest_path),
            "sample_count": len(samples),
        },
        "output_manifest": {
            "sha256": sha256_file(output_manifest),
            "sample_count": len(retained_samples),
        },
        "image_validation": {
            "decoded": len(records),
            "invalid": 0,
            "portrait": 0,
            "min_label_chars": min(record.label_chars for record in records),
            "max_label_chars": max(record.label_chars for record in records),
        },
        "deduplication": duplicate_report,
        "splits": split_counts,
        "forbidden_run_ids": sorted(forbidden_runs),
        "forbidden_samples": 0,
        "train_validation_image_sha_overlap": 0,
    }
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManifestAuditError as error:
        print(f"error: {error}")
        raise SystemExit(1) from error
