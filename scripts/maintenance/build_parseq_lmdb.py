"""Build isolated PARSeq LMDB datasets from a private line-crop manifest."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any


_MIB = 1024**2
_MIN_MAP_SIZE = 256 * _MIB
_MAP_SIZE_QUANTUM = 64 * _MIB
_PER_SAMPLE_OVERHEAD = 1024
_MAP_SIZE_MARGIN = 1.5


def split_samples(
    samples: Iterable[dict[str, Any]],
    *,
    validation_run_ids: set[int],
    forbidden_run_ids: set[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(
        samples,
        key=lambda item: (
            int(item["run_id"]),
            int(item["page_no"]),
            int(item["segment_index"]),
        ),
    )
    present_ids = {int(item["run_id"]) for item in ordered}
    forbidden = present_ids & forbidden_run_ids
    if forbidden:
        raise ValueError(
            f"private manifest contains final holdout runs: {sorted(forbidden)}"
        )
    missing_validation = validation_run_ids - present_ids
    if missing_validation:
        raise ValueError(
            f"validation runs are absent from private manifest: {sorted(missing_validation)}"
        )
    train = [item for item in ordered if int(item["run_id"]) not in validation_run_ids]
    validation = [item for item in ordered if int(item["run_id"]) in validation_run_ids]
    if not train or not validation:
        raise ValueError("both train and validation splits must be non-empty")
    return train, validation


def estimate_lmdb_size(samples: list[dict[str, Any]]) -> dict[str, int]:
    image_bytes = sum(Path(sample["image"]).stat().st_size for sample in samples)
    label_bytes = sum(len(str(sample["label"]).encode("utf-8")) for sample in samples)
    estimated_bytes = (
        image_bytes + label_bytes + len(samples) * _PER_SAMPLE_OVERHEAD + 64 * 1024
    )
    required_bytes = math.ceil(estimated_bytes * _MAP_SIZE_MARGIN)
    map_size = max(
        _MIN_MAP_SIZE,
        math.ceil(required_bytes / _MAP_SIZE_QUANTUM) * _MAP_SIZE_QUANTUM,
    )
    return {
        "samples": len(samples),
        "image_bytes": image_bytes,
        "label_bytes": label_bytes,
        "estimated_bytes": estimated_bytes,
        "map_size": map_size,
    }


def _write_lmdb(
    samples: list[dict[str, Any]], output_dir: Path, *, map_size: int
) -> None:
    import lmdb

    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"LMDB output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    env = lmdb.open(str(output_dir), map_size=map_size)
    with env.begin(write=True) as transaction:
        for index, sample in enumerate(samples, start=1):
            image_bytes = Path(sample["image"]).read_bytes()
            label = str(sample["label"])
            transaction.put(f"image-{index:09d}".encode(), image_bytes)
            transaction.put(f"label-{index:09d}".encode(), label.encode("utf-8"))
        transaction.put(b"num-samples", str(len(samples)).encode())
    env.sync()
    env.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validation-run-id", action="append", type=int, required=True)
    parser.add_argument("--forbidden-run-id", action="append", type=int, default=[])
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.audit_output.exists():
        raise ValueError(f"audit output already exists: {args.audit_output}")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    train, validation = split_samples(
        manifest["samples"],
        validation_run_ids=set(args.validation_run_id),
        forbidden_run_ids=set(args.forbidden_run_id),
    )
    train_size = estimate_lmdb_size(train)
    validation_size = estimate_lmdb_size(validation)
    _write_lmdb(
        train, args.output_root / "train" / "real", map_size=train_size["map_size"]
    )
    _write_lmdb(
        validation,
        args.output_root / "val",
        map_size=validation_size["map_size"],
    )
    report = {
        "contains_page_text": False,
        "contains_page_images": False,
        "validation_run_ids": sorted(set(args.validation_run_id)),
        "forbidden_run_ids": sorted(set(args.forbidden_run_id)),
        "train_run_ids": sorted({int(item["run_id"]) for item in train}),
        "train_samples": len(train),
        "train_label_chars": sum(int(item["label_chars"]) for item in train),
        "validation_samples": len(validation),
        "validation_label_chars": sum(int(item["label_chars"]) for item in validation),
        "lmdb_size": {
            "train": train_size,
            "validation": validation_size,
            "margin_multiplier": _MAP_SIZE_MARGIN,
            "rounding_quantum_bytes": _MAP_SIZE_QUANTUM,
            "minimum_map_size_bytes": _MIN_MAP_SIZE,
            "per_sample_overhead_bytes": _PER_SAMPLE_OVERHEAD,
        },
    }
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"train={len(train)} samples; validation={len(validation)} samples; "
        f"validation_runs={report['validation_run_ids']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
