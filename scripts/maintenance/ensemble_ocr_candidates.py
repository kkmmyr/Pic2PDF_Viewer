"""Build a ground-truth-independent character-aligned OCR consensus report."""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_BENCHMARK_PATH = Path(__file__).with_name("benchmark_ocr_ground_truth.py")
_SPEC = importlib.util.spec_from_file_location("ocr_benchmark", _BENCHMARK_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"could not load OCR benchmark module: {_BENCHMARK_PATH}")
benchmark = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(benchmark)


def align_to_pivot(pivot: str, candidate: str) -> tuple[list[str | None], list[str]]:
    """Align candidate characters and between-character insertions to a pivot."""
    row_count = len(pivot)
    column_count = len(candidate)
    directions = [bytearray(column_count + 1) for _ in range(row_count + 1)]
    for column_index in range(1, column_count + 1):
        directions[0][column_index] = 3
    previous = list(range(column_count + 1))
    for row_index, pivot_char in enumerate(pivot, start=1):
        current = [row_index]
        directions[row_index][0] = 2
        for column_index, candidate_char in enumerate(candidate, start=1):
            substitution = previous[column_index - 1] + (pivot_char != candidate_char)
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

    aligned: list[str | None] = [None] * row_count
    reverse_gaps: list[list[str]] = [[] for _ in range(row_count + 1)]
    row_index = row_count
    column_index = column_count
    while row_index or column_index:
        direction = directions[row_index][column_index]
        if direction == 1:
            aligned[row_index - 1] = candidate[column_index - 1]
            row_index -= 1
            column_index -= 1
        elif direction == 2:
            row_index -= 1
        else:
            reverse_gaps[row_index].append(candidate[column_index - 1])
            column_index -= 1
    gaps = ["".join(reversed(characters)) for characters in reverse_gaps]
    return aligned, gaps


def _distance_ratio(left: str, right: str) -> float:
    distance = benchmark._edit_distance(left, right)
    return distance / max(1, len(left), len(right))


def select_medoid(candidates: list[tuple[str, str]]) -> int:
    """Select the candidate with minimum total normalized peer distance."""
    totals = []
    for left_index, (_, left_text) in enumerate(candidates):
        total = sum(
            _distance_ratio(left_text, right_text)
            for right_index, (_, right_text) in enumerate(candidates)
            if right_index != left_index
        )
        totals.append((total, left_index))
    return min(totals)[1]


def character_consensus(
    candidates: list[tuple[str, str]],
    *,
    min_char_support: int = 2,
    min_delete_support: int = 3,
    min_gap_support: int = 2,
) -> tuple[str, dict[str, Any]]:
    normalized_candidates = [
        (engine, benchmark._normalize_text(text)) for engine, text in candidates
    ]
    if not normalized_candidates:
        raise ValueError("at least one OCR candidate is required")
    pivot_index = select_medoid(normalized_candidates)
    pivot_engine, pivot = normalized_candidates[pivot_index]
    alignments = []
    for engine, text in normalized_candidates:
        if text == pivot:
            aligned = list(pivot)
            gaps = [""] * (len(pivot) + 1)
        else:
            aligned, gaps = align_to_pivot(pivot, text)
        alignments.append((engine, aligned, gaps))

    output: list[str] = []
    changed_characters = deleted_characters = inserted_characters = 0
    accepted_gaps = []
    for position in range(len(pivot) + 1):
        gap_counts = Counter(
            gaps[position] for _, _, gaps in alignments if gaps[position]
        )
        supported_gaps = [
            (support, len(text), text)
            for text, support in gap_counts.items()
            if support >= min_gap_support
        ]
        if supported_gaps:
            support, _, gap_text = max(supported_gaps)
            output.append(gap_text)
            inserted_characters += len(gap_text)
            accepted_gaps.append(
                {"pivot_position": position, "text": gap_text, "support": support}
            )
        if position == len(pivot):
            continue

        values = [aligned[position] for _, aligned, _ in alignments]
        delete_support = sum(value is None for value in values)
        if delete_support >= min_delete_support:
            deleted_characters += 1
            continue
        char_counts = Counter(value for value in values if value is not None)
        best_support = max(char_counts.values())
        best_chars = sorted(
            char for char, support in char_counts.items() if support == best_support
        )
        pivot_char = pivot[position]
        if best_support < min_char_support or len(best_chars) > 1:
            chosen = pivot_char
        else:
            chosen = best_chars[0]
        output.append(chosen)
        changed_characters += int(chosen != pivot_char)

    return "".join(output), {
        "pivot_engine": pivot_engine,
        "candidate_count": len(normalized_candidates),
        "changed_characters": changed_characters,
        "deleted_characters": deleted_characters,
        "inserted_characters": inserted_characters,
        "accepted_gaps": accepted_gaps,
    }


def ensemble_reports(
    corpus: dict[str, Any],
    reports: list[dict[str, Any]],
    *,
    min_char_support: int = 2,
    min_delete_support: int = 3,
    min_gap_support: int = 2,
) -> dict[str, Any]:
    if len(reports) < 3:
        raise ValueError("at least three candidate reports are required")
    report_maps = [
        (
            str(report["engine"]),
            {int(page["entry_id"]): page for page in report["pages"]},
        )
        for report in reports
    ]
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

    hypotheses: dict[int, str] = {}
    decisions: dict[int, dict[str, Any]] = {}
    for entry in entries:
        entry_id = int(entry["id"])
        expected_sha = str(entry["image_sha256"])
        candidates = []
        for engine, pages in report_maps:
            page = pages.get(entry_id)
            if page is None:
                continue
            if str(page["image_sha256"]) != expected_sha:
                raise ValueError(
                    f"image SHA-256 mismatch for entry {entry_id} in {engine}"
                )
            candidates.append((engine, str(page["hypothesis"])))
        hypothesis, decision = character_consensus(
            candidates,
            min_char_support=min_char_support,
            min_delete_support=min_delete_support,
            min_gap_support=min_gap_support,
        )
        hypotheses[entry_id] = hypothesis
        decisions[entry_id] = decision

    result = benchmark.summarize(entries, hypotheses, "character-consensus")
    for page in result["pages"]:
        page["consensus_decision"] = decisions[int(page["entry_id"])]
    result["consensus_policy"] = {
        "candidate_engines": [engine for engine, _ in report_maps],
        "pivot": "minimum-total-normalized-peer-distance",
        "min_char_support": min_char_support,
        "min_delete_support": min_delete_support,
        "min_gap_support": min_gap_support,
        "ground_truth_used_for_selection": False,
    }
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--corpus-json", type=Path)
    parser.add_argument("--candidate-report", type=Path, action="append", required=True)
    parser.add_argument("--policy", type=Path, default=benchmark.DEFAULT_POLICY_PATH)
    parser.add_argument("--min-char-support", type=int, default=2)
    parser.add_argument("--min-delete-support", type=int, default=3)
    parser.add_argument("--min-gap-support", type=int, default=2)
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
    result = ensemble_reports(
        corpus,
        reports,
        min_char_support=args.min_char_support,
        min_delete_support=args.min_delete_support,
        min_gap_support=args.min_gap_support,
    )
    result_entry_ids = {int(page["entry_id"]) for page in result["pages"]}
    scoped_corpus = {
        **corpus,
        "entries": [
            entry for entry in corpus["entries"] if int(entry["id"]) in result_entry_ids
        ],
    }
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    result["quality_gate"] = benchmark.evaluate_quality_gate(
        scoped_corpus, result, policy
    )
    benchmark._print_summary(result)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
