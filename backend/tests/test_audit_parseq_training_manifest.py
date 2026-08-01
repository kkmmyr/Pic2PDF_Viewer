from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "audit_parseq_training_manifest.py"
SPEC = importlib.util.spec_from_file_location("audit_parseq_training_manifest", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def record(index: int, image_hash: str, label: str) -> object:
    return MODULE.SampleRecord(
        index=index,
        run_id=index + 1,
        page_no=1,
        segment_index=1,
        image_path=f"{index}.jpg",
        image_sha256=image_hash,
        width=100,
        height=20,
        label_chars=len(label),
        label=label,
    )


def test_deduplicate_records_retains_one_same_label_image() -> None:
    retained, report = MODULE.deduplicate_records(
        [record(0, "same", "本文です"), record(1, "same", "本文です")],
        excluded_conflict_hashes=set(),
    )

    assert len(retained) == 1
    assert report["same_label_duplicate_samples_removed"] == 1


def test_deduplicate_records_rejects_unreviewed_conflict() -> None:
    with pytest.raises(MODULE.ManifestAuditError, match="require review"):
        MODULE.deduplicate_records(
            [record(0, "conflict", "わかりました"), record(1, "conflict", "おかりました")],
            excluded_conflict_hashes=set(),
        )


def test_deduplicate_records_excludes_reviewed_conflict_group() -> None:
    retained, report = MODULE.deduplicate_records(
        [record(0, "conflict", "わかりました"), record(1, "conflict", "おかりました")],
        excluded_conflict_hashes={"conflict"},
    )

    assert retained == []
    assert report["conflicting_samples_removed"] == 2
