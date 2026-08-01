from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "merge_ocr_consensus_gaps.py"
_SPEC = importlib.util.spec_from_file_location("merge_ocr_consensus_gaps", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
merge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(merge)


def test_merge_supported_gaps_requires_two_anchored_exact_candidates() -> None:
    primary = "abcdefghijUVWXYZklmnopqrst"
    alternatives = [
        ("a", "abcdefghijMISSINGUVWXYZklmnopqrst"),
        ("b", "abcdefghijMISSINGUVWXYZklmnopqrst"),
        ("c", "abcdefghijDIFFERENTUVWXYZklmnopqrst"),
    ]

    merged, proposals = merge.merge_supported_gaps(primary, alternatives, anchor_chars=6)

    assert merged == "abcdefghijMISSINGUVWXYZklmnopqrst"
    assert proposals == [
        {
            "primary_index": 10,
            "text": "MISSING",
            "supporting_engines": ["a", "b"],
            "support_count": 2,
        }
    ]


def test_merge_supported_gaps_rejects_single_candidate() -> None:
    primary = "abcdefghijUVWXYZklmnopqrst"

    merged, proposals = merge.merge_supported_gaps(
        primary,
        [("a", "abcdefghijMISSINGUVWXYZklmnopqrst")],
        anchor_chars=6,
    )

    assert merged == primary
    assert proposals == []


def test_merge_reports_scopes_corpus_to_primary_report() -> None:
    entry = {
        "id": 1,
        "run_id": 10,
        "page_no": 2,
        "page_type": "narrative",
        "layout_type": "normal_prose",
        "reference_text": "abcdefghijMISSINGUVWXYZklmnopqrst",
        "image_sha256": "sha",
        "state": "verified",
    }
    unused = {**entry, "id": 2, "image_sha256": "unused"}
    primary = {
        "engine": "primary",
        "pages": [{"entry_id": 1, "image_sha256": "sha", "hypothesis": "abcdefghijUVWXYZklmnopqrst"}],
    }
    alternatives = [
        {
            "engine": name,
            "pages": [
                {
                    "entry_id": 1,
                    "image_sha256": "sha",
                    "hypothesis": "abcdefghijMISSINGUVWXYZklmnopqrst",
                }
            ],
        }
        for name in ("a", "b")
    ]

    report = merge.merge_reports(
        {"entries": [entry, unused]},
        primary,
        alternatives,
        min_support=2,
        min_chars=4,
        max_chars=80,
        anchor_chars=6,
        eligible_layout_types={"normal_prose"},
    )

    assert [page["entry_id"] for page in report["pages"]] == [1]
