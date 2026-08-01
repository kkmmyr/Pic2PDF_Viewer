"""Compare OCR benchmark reports and calculate diagnostic oracle bounds.

The oracle values use verified ground truth and must never be used as published OCR.

Example:
    uv run python scripts/maintenance/compare_ocr_benchmarks.py \
        --candidate-report current.json \
        --candidate-report ndlocr.json \
        --output oracle.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BENCHMARK_PATH = Path(__file__).with_name("benchmark_ocr_ground_truth.py")
_SPEC = importlib.util.spec_from_file_location("ocr_benchmark", _BENCHMARK_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"could not load OCR benchmark module: {_BENCHMARK_PATH}")
benchmark = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(benchmark)


def matched_reference_positions(reference: str, hypothesis: str) -> set[int]:
    """Return reference indexes matched exactly in one optimal Levenshtein alignment."""
    normalized_reference = benchmark._normalize_text(reference)
    normalized_hypothesis = benchmark._normalize_text(hypothesis)
    row_count = len(normalized_reference)
    column_count = len(normalized_hypothesis)
    directions = [bytearray(column_count + 1) for _ in range(row_count + 1)]
    for column_index in range(1, column_count + 1):
        directions[0][column_index] = 3
    previous = list(range(column_count + 1))
    for row_index, reference_char in enumerate(normalized_reference, start=1):
        current = [row_index]
        directions[row_index][0] = 2
        for column_index, hypothesis_char in enumerate(normalized_hypothesis, start=1):
            substitution = previous[column_index - 1] + (
                reference_char != hypothesis_char
            )
            deletion = previous[column_index] + 1
            insertion = current[column_index - 1] + 1
            if substitution <= deletion and substitution <= insertion:
                current.append(substitution)
                directions[row_index][column_index] = 1
            elif deletion <= insertion:
                current.append(deletion)
                directions[row_index][column_index] = 2
            else:
                current.append(insertion)
                directions[row_index][column_index] = 3
        previous = current

    matched: set[int] = set()
    row_index = row_count
    column_index = column_count
    while row_index or column_index:
        direction = directions[row_index][column_index]
        if direction == 1:
            if (
                normalized_reference[row_index - 1]
                == normalized_hypothesis[column_index - 1]
            ):
                matched.add(row_index - 1)
            row_index -= 1
            column_index -= 1
        elif direction == 2:
            row_index -= 1
        else:
            column_index -= 1
    return matched


def _report_pages(report: dict[str, Any]) -> dict[int, dict[str, Any]]:
    pages: dict[int, dict[str, Any]] = {}
    for page in report["pages"]:
        entry_id = int(page["entry_id"])
        if entry_id in pages:
            raise ValueError(f"duplicate entry {entry_id} in report {report['engine']}")
        pages[entry_id] = page
    return pages


def compare_reports(
    corpus: dict[str, Any], reports: list[dict[str, Any]]
) -> dict[str, Any]:
    if len(reports) < 2:
        raise ValueError("at least two candidate reports are required")
    report_maps = [(str(report["engine"]), _report_pages(report)) for report in reports]
    primary_entry_ids = set(report_maps[0][1])
    entries = [
        entry
        for entry in corpus["entries"]
        if entry["state"] == "verified" and int(entry["id"]) in primary_entry_ids
    ]
    if len(entries) != len(primary_entry_ids):
        found_entry_ids = {int(entry["id"]) for entry in entries}
        raise ValueError(
            "primary report entries are not all verified in corpus: "
            f"{sorted(primary_entry_ids - found_entry_ids)}"
        )
    chosen_hypotheses: dict[int, str] = {}
    selected_engines: dict[int, str] = {}
    per_page_reference_oracle: list[dict[str, Any]] = []
    reference_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"page_count": 0, "reference_chars": 0, "misses": 0}
    )

    for entry in entries:
        entry_id = int(entry["id"])
        reference = str(entry["reference_text"])
        candidates: list[tuple[int, str, str]] = []
        matched_union: set[int] = set()
        candidate_distances: dict[str, int] = {}
        for engine, pages in report_maps:
            page = pages.get(entry_id)
            if page is None:
                continue
            expected_sha = str(entry["image_sha256"])
            actual_sha = str(page["image_sha256"])
            if actual_sha != expected_sha:
                raise ValueError(
                    f"image SHA-256 mismatch for entry {entry_id} in {engine}: "
                    f"expected {expected_sha}, got {actual_sha}"
                )
            hypothesis = str(page["hypothesis"])
            distance, _, _ = benchmark.character_error_rate(reference, hypothesis)
            candidate_distances[engine] = distance
            candidates.append((distance, engine, hypothesis))
            matched_union.update(matched_reference_positions(reference, hypothesis))
        if not candidates:
            raise ValueError(f"no candidate hypothesis for verified entry {entry_id}")

        distance, engine, hypothesis = min(
            candidates, key=lambda item: (item[0], item[1])
        )
        chosen_hypotheses[entry_id] = hypothesis
        selected_engines[entry_id] = engine
        reference_chars = len(benchmark._normalize_text(reference))
        misses = reference_chars - len(matched_union)
        page_type = str(entry["page_type"])
        layout_type = str(entry.get("layout_type", "unknown"))
        for group in ("overall", page_type, f"layout:{layout_type}"):
            reference_totals[group]["page_count"] += 1
            reference_totals[group]["reference_chars"] += reference_chars
            reference_totals[group]["misses"] += misses
        per_page_reference_oracle.append(
            {
                "entry_id": entry_id,
                "run_id": int(entry["run_id"]),
                "page_no": int(entry["page_no"]),
                "page_type": page_type,
                "layout_type": layout_type,
                "reference_chars": reference_chars,
                "matched_positions": len(matched_union),
                "misses": misses,
                "miss_rate": misses / reference_chars if reference_chars else None,
                "page_oracle_engine": engine,
                "page_oracle_edit_distance": distance,
                "candidate_edit_distances": candidate_distances,
            }
        )

    page_oracle = benchmark.summarize(entries, chosen_hypotheses, "page-oracle")
    for page in page_oracle["pages"]:
        page["selected_engine"] = selected_engines[int(page["entry_id"])]

    ordered_groups = (
        "overall",
        *benchmark.PAGE_TYPE_ORDER,
        *(f"layout:{layout}" for layout in benchmark.LAYOUT_TYPE_ORDER),
    )
    reference_metrics = []
    for group in ordered_groups:
        values = reference_totals[group]
        if values["page_count"] == 0:
            continue
        reference_chars = values["reference_chars"]
        reference_metrics.append(
            {
                "group": group,
                **values,
                "miss_rate": (
                    values["misses"] / reference_chars if reference_chars else None
                ),
            }
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "diagnostic_only": True,
        "candidates": [engine for engine, _ in report_maps],
        "page_oracle": page_oracle,
        "reference_position_oracle": {
            "metrics": reference_metrics,
            "pages": per_page_reference_oracle,
        },
    }


def _print_summary(result: dict[str, Any]) -> None:
    print(f"candidates: {', '.join(result['candidates'])}")
    page_metrics = {
        metric["group"]: metric for metric in result["page_oracle"]["metrics"]
    }
    reference_metrics = {
        metric["group"]: metric
        for metric in result["reference_position_oracle"]["metrics"]
    }
    for group in ("overall", "layout:normal_prose"):
        page_metric = page_metrics.get(group)
        reference_metric = reference_metrics.get(group)
        if page_metric is None or reference_metric is None:
            continue
        print(
            f"{group}: page_oracle_CER={page_metric['aggregate_cer'] * 100:.3f}%, "
            f"reference_position_miss_rate={reference_metric['miss_rate'] * 100:.3f}%"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--corpus-json", type=Path)
    parser.add_argument("--candidate-report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    corpus = (
        json.loads(args.corpus_json.read_text(encoding="utf-8"))
        if args.corpus_json is not None
        else benchmark._get_json(f"{args.api_base.rstrip('/')}/api/ocr/ground-truth")
    )
    reports = [
        json.loads(path.read_text(encoding="utf-8")) for path in args.candidate_report
    ]
    result = compare_reports(corpus, reports)
    _print_summary(result)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
