"""OCR benchmark corpus selection, reporting, and quality gates."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from ocr_benchmark_text import (
    NORMALIZATION_VERSION,
    character_error_details,
)

PAGE_TYPE_ORDER = ("narrative", "toc", "illustration", "colophon_or_ad", "unknown")
LAYOUT_TYPE_ORDER = (
    "normal_prose",
    "full_width",
    "mixed_illustration",
    "structured",
    "image_only",
    "unknown",
)


def filter_entries(
    entries: list[dict[str, Any]],
    *,
    entry_ids: set[int] | None,
    run_ids: set[int] | None,
) -> list[dict[str, Any]]:
    selected = entries
    if entry_ids:
        selected = [item for item in selected if int(item["id"]) in entry_ids]
        missing = entry_ids - {int(item["id"]) for item in selected}
        if missing:
            raise ValueError(
                f"verified ground-truth entries not found: {sorted(missing)}"
            )
    if run_ids:
        selected = [item for item in selected if int(item["run_id"]) in run_ids]
        missing = run_ids - {int(item["run_id"]) for item in selected}
        if missing:
            raise ValueError(f"verified ground-truth runs not found: {sorted(missing)}")
    return selected


def summarize(
    entries: list[dict[str, Any]],
    hypotheses: dict[int, str],
    engine: str,
    segments_by_entry: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"page_count": 0, "total_edit_distance": 0, "total_reference_chars": 0}
    )
    pages = []
    for entry in entries:
        entry_id = int(entry["id"])
        hypothesis = hypotheses[entry_id]
        error_details = character_error_details(
            str(entry["reference_text"]), hypothesis
        )
        distance = int(error_details["edit_distance"])
        reference_chars = int(error_details["reference_chars"])
        cer = error_details["cer"]
        page_type = str(entry["page_type"])
        layout_type = str(entry.get("layout_type", "unknown"))
        for group in ("overall", page_type, f"layout:{layout_type}"):
            totals[group]["page_count"] += 1
            totals[group]["total_edit_distance"] += distance
            totals[group]["total_reference_chars"] += reference_chars
        page = {
            "entry_id": entry_id,
            "run_id": int(entry["run_id"]),
            "page_no": int(entry["page_no"]),
            "page_type": page_type,
            "layout_type": layout_type,
            "image_sha256": str(entry["image_sha256"]),
            "edit_distance": distance,
            "reference_chars": reference_chars,
            "cer": cer,
            "substitutions": error_details["substitutions"],
            "deletions": error_details["deletions"],
            "insertions": error_details["insertions"],
            "deletion_rate": error_details["deletion_rate"],
            "hypothesis": hypothesis,
        }
        if segments_by_entry is not None:
            page["segments"] = segments_by_entry.get(entry_id, [])
        pages.append(page)

    metrics = []
    ordered_groups = (
        "overall",
        *PAGE_TYPE_ORDER,
        *(f"layout:{layout_type}" for layout_type in LAYOUT_TYPE_ORDER),
    )
    for group in ordered_groups:
        values = totals[group]
        if values["page_count"] == 0:
            continue
        reference_chars = values["total_reference_chars"]
        metrics.append(
            {
                "group": group,
                **values,
                "aggregate_cer": (
                    values["total_edit_distance"] / reference_chars
                    if reference_chars
                    else None
                ),
            }
        )
    return {
        "engine": engine,
        "normalization_version": NORMALIZATION_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "pages": pages,
    }


def _print_summary(report: dict[str, Any]) -> None:
    print(f"engine: {report['engine']}")
    for metric in report["metrics"]:
        cer = metric["aggregate_cer"]
        cer_text = "—" if cer is None else f"{cer * 100:.2f}%"
        print(
            f"{metric['group']}: pages={metric['page_count']}, "
            f"chars={metric['total_reference_chars']}, CER={cer_text}"
        )
    quality_gate = report.get("quality_gate")
    if quality_gate is not None:
        print(f"quality_gate: {'PASS' if quality_gate['passed'] else 'FAIL'}")
        for check in quality_gate["checks"]:
            status = "PASS" if check["passed"] else "FAIL"
            print(
                f"  {status} {check['name']}: actual={check['actual']}, "
                f"threshold={check['threshold']}"
            )
