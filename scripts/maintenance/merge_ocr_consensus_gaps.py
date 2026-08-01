"""Merge only independently supported, anchored omissions into a primary OCR report."""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_BENCHMARK_PATH = Path(__file__).with_name("benchmark_ocr_ground_truth.py")
_SPEC = importlib.util.spec_from_file_location("ocr_benchmark", _BENCHMARK_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"could not load OCR benchmark module: {_BENCHMARK_PATH}")
benchmark = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(benchmark)


def insertion_proposals(
    primary: str,
    alternative: str,
    *,
    min_chars: int,
    max_chars: int,
    anchor_chars: int,
) -> list[tuple[int, str]]:
    matcher = difflib.SequenceMatcher(a=primary, b=alternative, autojunk=False)
    opcodes = matcher.get_opcodes()
    proposals = []
    for opcode_index, (
        tag,
        primary_start,
        primary_end,
        alt_start,
        alt_end,
    ) in enumerate(opcodes):
        if tag != "insert" or primary_start != primary_end:
            continue
        inserted_text = alternative[alt_start:alt_end]
        if not min_chars <= len(inserted_text) <= max_chars:
            continue
        previous_equal = (
            opcode_index > 0
            and opcodes[opcode_index - 1][0] == "equal"
            and opcodes[opcode_index - 1][2] - opcodes[opcode_index - 1][1]
            >= anchor_chars
        )
        next_equal = (
            opcode_index + 1 < len(opcodes)
            and opcodes[opcode_index + 1][0] == "equal"
            and opcodes[opcode_index + 1][2] - opcodes[opcode_index + 1][1]
            >= anchor_chars
        )
        if (
            previous_equal
            and next_equal
            and any(char.isalnum() for char in inserted_text)
        ):
            proposals.append((primary_start, inserted_text))
    return proposals


def merge_supported_gaps(
    primary: str,
    alternatives: list[tuple[str, str]],
    *,
    min_support: int = 2,
    min_chars: int = 4,
    max_chars: int = 80,
    anchor_chars: int = 8,
) -> tuple[str, list[dict[str, Any]]]:
    normalized_primary = benchmark._normalize_text(primary)
    support: dict[tuple[int, str], set[str]] = defaultdict(set)
    for engine, alternative in alternatives:
        normalized_alternative = benchmark._normalize_text(alternative)
        for proposal in insertion_proposals(
            normalized_primary,
            normalized_alternative,
            min_chars=min_chars,
            max_chars=max_chars,
            anchor_chars=anchor_chars,
        ):
            support[proposal].add(engine)

    accepted = [
        {
            "primary_index": primary_index,
            "text": text,
            "supporting_engines": sorted(engines),
            "support_count": len(engines),
        }
        for (primary_index, text), engines in support.items()
        if len(engines) >= min_support
    ]
    accepted.sort(
        key=lambda proposal: (
            int(proposal["primary_index"]),
            -int(proposal["support_count"]),
            -len(str(proposal["text"])),
        )
    )
    non_conflicting = []
    seen_indexes: set[int] = set()
    for proposal in accepted:
        primary_index = int(proposal["primary_index"])
        if primary_index in seen_indexes:
            continue
        seen_indexes.add(primary_index)
        non_conflicting.append(proposal)

    merged = normalized_primary
    for proposal in sorted(
        non_conflicting, key=lambda item: int(item["primary_index"]), reverse=True
    ):
        primary_index = int(proposal["primary_index"])
        merged = merged[:primary_index] + str(proposal["text"]) + merged[primary_index:]
    return merged, non_conflicting


def merge_reports(
    corpus: dict[str, Any],
    primary_report: dict[str, Any],
    alternative_reports: list[dict[str, Any]],
    *,
    min_support: int,
    min_chars: int,
    max_chars: int,
    anchor_chars: int,
    eligible_layout_types: set[str],
) -> dict[str, Any]:
    primary_pages = {int(page["entry_id"]): page for page in primary_report["pages"]}
    entries = [
        entry
        for entry in corpus["entries"]
        if entry["state"] == "verified" and int(entry["id"]) in primary_pages
    ]
    if len(entries) != len(primary_pages):
        found_entry_ids = {int(entry["id"]) for entry in entries}
        raise ValueError(
            "primary report entries are not all verified in corpus: "
            f"{sorted(set(primary_pages) - found_entry_ids)}"
        )
    alternative_pages = [
        (
            str(report["engine"]),
            {int(page["entry_id"]): page for page in report["pages"]},
        )
        for report in alternative_reports
    ]
    hypotheses: dict[int, str] = {}
    proposals_by_entry: dict[int, list[dict[str, Any]]] = {}
    for entry in entries:
        entry_id = int(entry["id"])
        primary_page = primary_pages.get(entry_id)
        if primary_page is None:
            raise ValueError(f"primary report has no entry {entry_id}")
        expected_sha = str(entry["image_sha256"])
        if str(primary_page["image_sha256"]) != expected_sha:
            raise ValueError(f"primary image SHA-256 mismatch for entry {entry_id}")
        alternatives = []
        for engine, pages in alternative_pages:
            page = pages.get(entry_id)
            if page is None:
                continue
            if str(page["image_sha256"]) != expected_sha:
                raise ValueError(
                    f"alternative image SHA-256 mismatch for entry {entry_id} in {engine}"
                )
            alternatives.append((engine, str(page["hypothesis"])))
        if str(entry.get("layout_type", "unknown")) in eligible_layout_types:
            merged, proposals = merge_supported_gaps(
                str(primary_page["hypothesis"]),
                alternatives,
                min_support=min_support,
                min_chars=min_chars,
                max_chars=max_chars,
                anchor_chars=anchor_chars,
            )
        else:
            merged = benchmark._normalize_text(str(primary_page["hypothesis"]))
            proposals = []
        hypotheses[entry_id] = merged
        proposals_by_entry[entry_id] = proposals

    report = benchmark.summarize(entries, hypotheses, "consensus-gap-merge")
    for page in report["pages"]:
        page["consensus_gap_proposals"] = proposals_by_entry[int(page["entry_id"])]
    report["merge_policy"] = {
        "primary_engine": str(primary_report["engine"]),
        "alternative_engines": [
            str(report["engine"]) for report in alternative_reports
        ],
        "min_support": min_support,
        "min_chars": min_chars,
        "max_chars": max_chars,
        "anchor_chars": anchor_chars,
        "eligible_layout_types": sorted(eligible_layout_types),
    }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--corpus-json", type=Path)
    parser.add_argument("--primary-report", type=Path, required=True)
    parser.add_argument(
        "--alternative-report", type=Path, action="append", required=True
    )
    parser.add_argument("--policy", type=Path, default=benchmark.DEFAULT_POLICY_PATH)
    parser.add_argument("--min-support", type=int, default=2)
    parser.add_argument("--min-chars", type=int, default=4)
    parser.add_argument("--max-chars", type=int, default=80)
    parser.add_argument("--anchor-chars", type=int, default=8)
    parser.add_argument("--eligible-layout-type", action="append")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-gate", action="store_true")
    args = parser.parse_args(argv)
    corpus = (
        json.loads(args.corpus_json.read_text(encoding="utf-8"))
        if args.corpus_json is not None
        else benchmark._get_json(f"{args.api_base.rstrip('/')}/api/ocr/ground-truth")
    )
    primary_report = json.loads(args.primary_report.read_text(encoding="utf-8"))
    alternatives = [
        json.loads(path.read_text(encoding="utf-8")) for path in args.alternative_report
    ]
    report = merge_reports(
        corpus,
        primary_report,
        alternatives,
        min_support=args.min_support,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
        anchor_chars=args.anchor_chars,
        eligible_layout_types=set(args.eligible_layout_type or ["normal_prose"]),
    )
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    report_entry_ids = {int(page["entry_id"]) for page in report["pages"]}
    scoped_corpus = {
        **corpus,
        "entries": [
            entry for entry in corpus["entries"] if int(entry["id"]) in report_entry_ids
        ],
    }
    report["quality_gate"] = benchmark.evaluate_quality_gate(
        scoped_corpus, report, policy
    )
    benchmark._print_summary(report)
    proposal_count = sum(
        len(page["consensus_gap_proposals"]) for page in report["pages"]
    )
    print(f"consensus_gap_proposals: {proposal_count}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 1 if args.fail_on_gate and not report["quality_gate"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
