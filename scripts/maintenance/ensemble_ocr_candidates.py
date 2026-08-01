"""Build a ground-truth-independent character-aligned OCR consensus report."""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from collections.abc import Sequence
from itertools import combinations
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
    return _candidate_distance_analysis(candidates)[0]


def _candidate_distance_analysis(
    candidates: list[tuple[str, str]],
) -> tuple[int, dict[str, float]]:
    totals = [0.0] * len(candidates)
    distances = []
    for left_index, right_index in combinations(range(len(candidates)), 2):
        distance = _distance_ratio(
            candidates[left_index][1], candidates[right_index][1]
        )
        totals[left_index] += distance
        totals[right_index] += distance
        distances.append(distance)
    pivot_index = min(range(len(candidates)), key=lambda index: (totals[index], index))
    return pivot_index, {
        "average_pairwise_distance": (
            sum(distances) / len(distances) if distances else 0.0
        ),
        "max_pairwise_distance": max(distances, default=0.0),
    }


def _aligned_text_window(
    aligned: list[str | None], start: int, length: int
) -> str | None:
    values = aligned[start : start + length]
    if len(values) != length or any(value is None for value in values):
        return None
    return "".join(value for value in values if value is not None)


def apply_supported_proper_noun_corrections(
    consensus: str,
    candidates: list[tuple[str, str]],
    terms: Sequence[str],
) -> tuple[str, dict[str, Any]]:
    """Apply only same-position, candidate-supported one-character corrections."""
    normalized_consensus = benchmark._normalize_text(consensus)
    normalized_candidates = [
        (engine, benchmark._normalize_text(text)) for engine, text in candidates
    ]
    alignments = [
        (engine, align_to_pivot(normalized_consensus, text)[0])
        for engine, text in normalized_candidates
    ]
    normalized_terms = sorted(
        {
            benchmark._normalize_text(str(term))
            for term in terms
            if len(benchmark._normalize_text(str(term))) >= 2
        },
        key=lambda value: (-len(value), value),
    )
    supported: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for term in normalized_terms:
        term_seen_on_page = any(term in text for _, text in normalized_candidates)
        for start in range(len(normalized_consensus) - len(term) + 1):
            end = start + len(term)
            variant = normalized_consensus[start:end]
            difference_count = sum(
                left != right for left, right in zip(variant, term, strict=True)
            )
            if difference_count != 1:
                continue
            exact_support = [
                engine
                for engine, aligned in alignments
                if _aligned_text_window(aligned, start, len(term)) == term
            ]
            variant_support = [
                engine
                for engine, aligned in alignments
                if _aligned_text_window(aligned, start, len(term)) == variant
            ]
            proposal = {
                "start": start,
                "end": end,
                "variant": variant,
                "term": term,
                "exact_support_engines": exact_support,
                "variant_support_engines": variant_support,
            }
            if exact_support:
                supported.append(proposal)
            elif term_seen_on_page and len(variant_support) >= 2:
                unresolved.append({**proposal, "reason": "no_exact_candidate_support"})

    ambiguous_indexes: set[int] = set()
    for left_index, right_index in combinations(range(len(supported)), 2):
        left = supported[left_index]
        right = supported[right_index]
        if int(left["start"]) < int(right["end"]) and int(right["start"]) < int(
            left["end"]
        ):
            ambiguous_indexes.update((left_index, right_index))

    applied = []
    output = list(normalized_consensus)
    for index, proposal in enumerate(supported):
        if index in ambiguous_indexes:
            unresolved.append({**proposal, "reason": "overlapping_supported_proposals"})
            continue
        start = int(proposal["start"])
        end = int(proposal["end"])
        output[start:end] = list(str(proposal["term"]))
        applied.append(proposal)
    return "".join(output), {
        "terms_considered": normalized_terms,
        "applied": applied,
        "unresolved": unresolved,
    }


def load_proper_noun_ledger(path: Path) -> dict[int, list[str]]:
    """Load a run-scoped ledger while rejecting page/ground-truth leakage."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise ValueError("proper noun ledger schema_version must be 1")
    allowed_document_keys = {"schema_version", "name", "scopes"}
    unknown_document_keys = set(document) - allowed_document_keys
    if unknown_document_keys:
        raise ValueError(
            "proper noun ledger has unsupported top-level keys: "
            f"{sorted(unknown_document_keys)}"
        )
    scopes = document.get("scopes")
    if not isinstance(scopes, list) or not scopes:
        raise ValueError("proper noun ledger scopes must be a non-empty list")
    terms_by_run: dict[int, list[str]] = {}
    for scope in scopes:
        if not isinstance(scope, dict):
            raise ValueError("proper noun ledger scope must be an object")
        unknown_scope_keys = set(scope) - {"series", "run_ids", "terms"}
        if unknown_scope_keys:
            raise ValueError(
                "proper noun ledger scope has unsupported keys: "
                f"{sorted(unknown_scope_keys)}"
            )
        run_ids = scope.get("run_ids")
        terms = scope.get("terms")
        if not isinstance(run_ids, list) or not run_ids:
            raise ValueError("proper noun ledger run_ids must be a non-empty list")
        if not isinstance(terms, list) or not terms:
            raise ValueError("proper noun ledger terms must be a non-empty list")
        normalized_terms = sorted(
            {benchmark._normalize_text(str(term)) for term in terms}
        )
        if any(len(term) < 2 for term in normalized_terms):
            raise ValueError("proper noun ledger terms must be at least two characters")
        for run_value in run_ids:
            run_id = int(run_value)
            if run_id <= 0 or run_id in terms_by_run:
                raise ValueError(
                    f"proper noun ledger run_id is invalid or repeated: {run_id}"
                )
            terms_by_run[run_id] = normalized_terms
    return terms_by_run


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
    pivot_index, distance_metrics = _candidate_distance_analysis(normalized_candidates)
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
        **distance_metrics,
    }


def ensemble_reports(
    corpus: dict[str, Any],
    reports: list[dict[str, Any]],
    *,
    min_char_support: int = 2,
    min_delete_support: int = 3,
    min_gap_support: int = 2,
    proper_noun_terms_by_run: dict[int, list[str]] | None = None,
    escalate_pairwise_distance: float | None = None,
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
    qa_escalation_entry_ids: list[int] = []
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
        terms = (proper_noun_terms_by_run or {}).get(int(entry["run_id"]), [])
        if terms:
            hypothesis, proper_noun_decision = apply_supported_proper_noun_corrections(
                hypothesis,
                candidates,
                terms,
            )
        else:
            proper_noun_decision = {
                "terms_considered": [],
                "applied": [],
                "unresolved": [],
            }
        escalation_reasons = []
        if proper_noun_decision["unresolved"]:
            escalation_reasons.append("unresolved_proper_noun")
        if (
            escalate_pairwise_distance is not None
            and float(decision["max_pairwise_distance"]) >= escalate_pairwise_distance
        ):
            escalation_reasons.append("candidate_pairwise_distance")
        decision["proper_noun_postprocess"] = proper_noun_decision
        decision["requires_codex_qa"] = bool(escalation_reasons)
        decision["codex_qa_reasons"] = escalation_reasons
        if escalation_reasons:
            qa_escalation_entry_ids.append(entry_id)
        hypotheses[entry_id] = hypothesis
        decisions[entry_id] = decision

    engine = (
        "character-consensus-proper-noun"
        if proper_noun_terms_by_run
        else "character-consensus"
    )
    result = benchmark.summarize(entries, hypotheses, engine)
    for page in result["pages"]:
        page["consensus_decision"] = decisions[int(page["entry_id"])]
    result["consensus_policy"] = {
        "candidate_engines": [engine for engine, _ in report_maps],
        "pivot": "minimum-total-normalized-peer-distance",
        "min_char_support": min_char_support,
        "min_delete_support": min_delete_support,
        "min_gap_support": min_gap_support,
        "ground_truth_used_for_selection": False,
        "proper_noun_ledger_enabled": bool(proper_noun_terms_by_run),
        "escalate_pairwise_distance": escalate_pairwise_distance,
    }
    result["qa_escalation"] = {
        "entry_ids": qa_escalation_entry_ids,
        "page_count": len(qa_escalation_entry_ids),
        "resolution_engine": None,
        "ground_truth_used_for_machine_candidate": False,
    }
    return result


def resolve_escalated_report(
    corpus: dict[str, Any],
    machine_report: dict[str, Any],
    qa_resolution_report: dict[str, Any],
) -> dict[str, Any]:
    """Replace only pre-declared escalations without recomputing the ensemble."""
    machine_pages = {int(page["entry_id"]): page for page in machine_report["pages"]}
    entry_ids = set(machine_pages)
    entries = [
        entry
        for entry in corpus["entries"]
        if entry["state"] == "verified" and int(entry["id"]) in entry_ids
    ]
    if len(entries) != len(entry_ids):
        found_entry_ids = {int(entry["id"]) for entry in entries}
        raise ValueError(
            "machine report entries are not all verified in corpus: "
            f"{sorted(entry_ids - found_entry_ids)}"
        )
    escalation_ids = {
        int(entry_id) for entry_id in machine_report["qa_escalation"]["entry_ids"]
    }
    if not escalation_ids <= entry_ids:
        raise ValueError("machine report escalation entries are outside its page set")
    resolution_pages = {
        int(page["entry_id"]): page for page in qa_resolution_report["pages"]
    }
    hypotheses = {
        entry_id: str(page["hypothesis"]) for entry_id, page in machine_pages.items()
    }
    for entry in entries:
        entry_id = int(entry["id"])
        if entry_id not in escalation_ids:
            continue
        resolution = resolution_pages.get(entry_id)
        if resolution is None:
            raise ValueError(f"QA resolution missing escalated entry {entry_id}")
        if str(resolution["image_sha256"]) != str(entry["image_sha256"]):
            raise ValueError(
                f"QA resolution image SHA-256 mismatch for entry {entry_id}"
            )
        hypotheses[entry_id] = str(resolution["hypothesis"])

    result = benchmark.summarize(
        entries, hypotheses, "character-consensus-codex-assisted"
    )
    for page in result["pages"]:
        machine_page = machine_pages[int(page["entry_id"])]
        page["consensus_decision"] = machine_page["consensus_decision"]
        page["resolved_by_codex"] = int(page["entry_id"]) in escalation_ids
    result["consensus_policy"] = machine_report["consensus_policy"]
    result["qa_escalation"] = {
        **machine_report["qa_escalation"],
        "resolution_engine": str(qa_resolution_report["engine"]),
        "resolved_entry_ids": sorted(escalation_ids),
    }
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--corpus-json", type=Path)
    parser.add_argument("--candidate-report", type=Path, action="append")
    parser.add_argument("--machine-report", type=Path)
    parser.add_argument("--policy", type=Path, default=benchmark.DEFAULT_POLICY_PATH)
    parser.add_argument("--min-char-support", type=int, default=2)
    parser.add_argument("--min-delete-support", type=int, default=3)
    parser.add_argument("--min-gap-support", type=int, default=2)
    parser.add_argument("--proper-noun-ledger", type=Path)
    parser.add_argument("--escalate-pairwise-distance", type=float)
    parser.add_argument("--qa-resolution-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    corpus = (
        json.loads(args.corpus_json.read_text(encoding="utf-8"))
        if args.corpus_json is not None
        else benchmark._get_json(f"{args.api_base.rstrip('/')}/api/ocr/ground-truth")
    )
    if args.machine_report is not None:
        if args.candidate_report:
            parser.error("--machine-report cannot be combined with --candidate-report")
        if args.qa_resolution_report is None:
            parser.error("--machine-report requires --qa-resolution-report")
        machine_report = json.loads(args.machine_report.read_text(encoding="utf-8"))
        qa_resolution_report = json.loads(
            args.qa_resolution_report.read_text(encoding="utf-8")
        )
        result = resolve_escalated_report(corpus, machine_report, qa_resolution_report)
    else:
        if not args.candidate_report:
            parser.error("at least one --candidate-report is required")
        if args.qa_resolution_report is not None:
            parser.error("--qa-resolution-report requires --machine-report")
        reports = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in args.candidate_report
        ]
        proper_noun_terms_by_run = (
            load_proper_noun_ledger(args.proper_noun_ledger)
            if args.proper_noun_ledger is not None
            else None
        )
        result = ensemble_reports(
            corpus,
            reports,
            min_char_support=args.min_char_support,
            min_delete_support=args.min_delete_support,
            min_gap_support=args.min_gap_support,
            proper_noun_terms_by_run=proper_noun_terms_by_run,
            escalate_pairwise_distance=args.escalate_pairwise_distance,
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
