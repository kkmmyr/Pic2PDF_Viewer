"""Benchmark OCR engines against the verified ground-truth corpus.

Examples:
    uv run python scripts/maintenance/benchmark_ocr_ground_truth.py current
    uv run python scripts/maintenance/benchmark_ocr_ground_truth.py tesseract \
        --tesseract "C:/Program Files/Tesseract-OCR/tesseract.exe" \
        --tessdata-dir "C:/path/to/tessdata-best"
    uv run python scripts/maintenance/benchmark_ocr_ground_truth.py yomitoku \
        --ocr-python "D:/61.tool/common/ocr/venv/Scripts/python.exe" \
        --ocr-path "D:/61.tool/common/ocr"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen

PAGE_TYPE_ORDER = ("narrative", "toc", "illustration", "colophon_or_ad", "unknown")
LAYOUT_TYPE_ORDER = (
    "normal_prose",
    "full_width",
    "mixed_illustration",
    "structured",
    "image_only",
    "unknown",
)
DEFAULT_POLICY_PATH = Path(__file__).with_name("ocr_quality_policy.json")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _edit_distance(reference: str, hypothesis: str) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row_index, reference_char in enumerate(reference, start=1):
        current = [row_index]
        for column_index, hypothesis_char in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column_index] + 1,
                    previous[column_index - 1] + (reference_char != hypothesis_char),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(
    reference: str, hypothesis: str
) -> tuple[int, int, float | None]:
    normalized_reference = _normalize_text(reference)
    normalized_hypothesis = _normalize_text(hypothesis)
    distance = _edit_distance(normalized_reference, normalized_hypothesis)
    reference_chars = len(normalized_reference)
    return (
        distance,
        reference_chars,
        distance / reference_chars if reference_chars else None,
    )


def character_error_details(
    reference: str, hypothesis: str
) -> dict[str, int | float | None]:
    """Return deterministic Levenshtein operation counts for omission screening."""
    normalized_reference = _normalize_text(reference)
    normalized_hypothesis = _normalize_text(hypothesis)
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

    substitutions = deletions = insertions = 0
    row_index = row_count
    column_index = column_count
    while row_index or column_index:
        direction = directions[row_index][column_index]
        if direction == 1:
            substitutions += int(
                normalized_reference[row_index - 1]
                != normalized_hypothesis[column_index - 1]
            )
            row_index -= 1
            column_index -= 1
        elif direction == 2:
            deletions += 1
            row_index -= 1
        else:
            insertions += 1
            column_index -= 1

    distance = previous[column_count]
    return {
        "edit_distance": distance,
        "reference_chars": row_count,
        "cer": distance / row_count if row_count else None,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "deletion_rate": deletions / row_count if row_count else None,
    }


def _get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=30) as response:  # noqa: S310 - operator supplied API URL
        return json.load(response)


def _download_images(
    entries: list[dict[str, Any]], api_base: str, images_dir: Path
) -> dict[int, Path]:
    image_paths: dict[int, Path] = {}
    for entry in entries:
        entry_id = int(entry["id"])
        image_url = urljoin(
            f"{api_base.rstrip('/')}/", str(entry["image_url"]).lstrip("/")
        )
        with urlopen(image_url, timeout=30) as response:  # noqa: S310 - same trusted API
            image_bytes = response.read()
        actual_sha256 = hashlib.sha256(image_bytes).hexdigest()
        expected_sha256 = str(entry["image_sha256"])
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"image SHA-256 mismatch for entry {entry_id}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        image_path = images_dir / f"{entry_id:04d}.png"
        image_path.write_bytes(image_bytes)
        image_paths[entry_id] = image_path
    return image_paths


def _run_tesseract(
    entries: list[dict[str, Any]],
    image_paths: dict[int, Path],
    executable: Path,
    tessdata_dir: Path,
) -> dict[int, str]:
    hypotheses: dict[int, str] = {}
    for entry in entries:
        entry_id = int(entry["id"])
        command = [
            str(executable),
            str(image_paths[entry_id]),
            "stdout",
            "--tessdata-dir",
            str(tessdata_dir),
            "-l",
            "jpn_vert",
            "--psm",
            "5",
        ]
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        hypotheses[entry_id] = result.stdout
    return hypotheses


def _run_yomitoku(
    entries: list[dict[str, Any]],
    image_paths: dict[int, Path],
    ocr_python: Path,
    ocr_path: Path,
    repo_root: Path,
    work_dir: Path,
) -> dict[int, str]:
    manifest_path = work_dir / "yomitoku-manifest.json"
    tasks = [
        {
            "book_name": str(entry["book_name"]),
            "page_no": int(entry["id"]),
            "image_path": str(image_paths[int(entry["id"])]),
        }
        for entry in entries
    ]
    manifest_path.write_text(
        json.dumps({"tasks": tasks}, ensure_ascii=False),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "OCR_ENGINE": "yomitoku",
        "OCR_PATH": str(ocr_path),
    }
    result = subprocess.run(
        [
            str(ocr_python),
            str(repo_root / "backend" / "services" / "novel_db" / "ocr_worker.py"),
            "--manifest",
            str(manifest_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    hypotheses: dict[int, str] = {}
    for line in result.stdout.splitlines():
        event = json.loads(line)
        if event.get("event") != "page":
            continue
        page = event["page"]
        entry_id = int(page["page_no"])
        if page["state"] != "passed":
            raise RuntimeError(
                f"yomitoku failed for entry {entry_id}: {page['error_message']}"
            )
        hypotheses[entry_id] = str(page["full_text"])
    missing = sorted(set(image_paths) - set(hypotheses))
    if missing:
        raise RuntimeError(f"yomitoku returned no result for entries: {missing}")
    return hypotheses


def summarize(
    entries: list[dict[str, Any]], hypotheses: dict[int, str], engine: str
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
        pages.append(
            {
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
        )

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
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "pages": pages,
    }


def _check(
    name: str, actual: Any, threshold: Any, passed: bool, **details: Any
) -> dict[str, Any]:
    return {
        "name": name,
        "actual": actual,
        "threshold": threshold,
        "passed": passed,
        **details,
    }


def evaluate_quality_gate(
    corpus: dict[str, Any], report: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    if int(policy.get("schema_version", 0)) != 1:
        raise ValueError("unsupported OCR quality policy schema_version")
    entries = [entry for entry in corpus["entries"] if entry["state"] == "verified"]
    pages = report["pages"]
    metrics = {metric["group"]: metric for metric in report["metrics"]}
    corpus_policy = policy["corpus"]
    quality_policy = policy["quality"]
    checks: list[dict[str, Any]] = []

    total_reference_chars = sum(
        len(_normalize_text(str(entry["reference_text"]))) for entry in entries
    )
    checks.append(
        _check(
            "corpus.verified_pages_min",
            len(entries),
            int(corpus_policy["min_verified_pages"]),
            len(entries) >= int(corpus_policy["min_verified_pages"]),
        )
    )
    checks.append(
        _check(
            "corpus.total_reference_chars_min",
            total_reference_chars,
            int(corpus_policy["min_total_reference_chars"]),
            total_reference_chars >= int(corpus_policy["min_total_reference_chars"]),
        )
    )
    for page_type, minimum in corpus_policy["min_page_type_counts"].items():
        actual = sum(entry["page_type"] == page_type for entry in entries)
        checks.append(
            _check(
                f"corpus.page_type.{page_type}_min",
                actual,
                int(minimum),
                actual >= int(minimum),
            )
        )
    for layout_type, minimum in corpus_policy["min_layout_type_counts"].items():
        actual = sum(
            entry.get("layout_type", "unknown") == layout_type for entry in entries
        )
        checks.append(
            _check(
                f"corpus.layout_type.{layout_type}_pages_min",
                actual,
                int(minimum),
                actual >= int(minimum),
            )
        )
    for layout_type, minimum in corpus_policy["min_layout_reference_chars"].items():
        actual = sum(
            len(_normalize_text(str(entry["reference_text"])))
            for entry in entries
            if entry.get("layout_type", "unknown") == layout_type
        )
        checks.append(
            _check(
                f"corpus.layout_type.{layout_type}_reference_chars_min",
                actual,
                int(minimum),
                actual >= int(minimum),
            )
        )

    for group, maximum in quality_policy["aggregate_cer_max_by_group"].items():
        metric = metrics.get(group)
        actual = metric.get("aggregate_cer") if metric else None
        checks.append(
            _check(
                f"quality.{group}.aggregate_cer_max",
                actual,
                float(maximum),
                actual is not None and float(actual) <= float(maximum),
            )
        )
    for layout_type, maximum in quality_policy["max_page_cer_by_layout"].items():
        scoped_pages = [page for page in pages if page["layout_type"] == layout_type]
        actual = max(
            (float(page["cer"]) for page in scoped_pages if page["cer"] is not None),
            default=None,
        )
        failed_entry_ids = [
            int(page["entry_id"])
            for page in scoped_pages
            if page["cer"] is None or float(page["cer"]) > float(maximum)
        ]
        checks.append(
            _check(
                f"quality.layout:{layout_type}.page_cer_max",
                actual,
                float(maximum),
                actual is not None and actual <= float(maximum),
                failed_entry_ids=failed_entry_ids,
            )
        )

    omission_policy = quality_policy["column_omission"]
    omission_suspects = [
        {
            "entry_id": int(page["entry_id"]),
            "run_id": int(page["run_id"]),
            "page_no": int(page["page_no"]),
            "deletions": int(page["deletions"]),
            "deletion_rate": page["deletion_rate"],
        }
        for page in pages
        if page["page_type"] == omission_policy["page_type"]
        and int(page["deletions"]) >= int(omission_policy["min_deleted_chars"])
        and page["deletion_rate"] is not None
        and float(page["deletion_rate"]) >= float(omission_policy["min_deletion_rate"])
    ]
    checks.append(
        _check(
            "quality.column_omission.suspect_pages_max",
            len(omission_suspects),
            int(omission_policy["max_suspect_pages"]),
            len(omission_suspects) <= int(omission_policy["max_suspect_pages"]),
            suspects=omission_suspects,
        )
    )

    entries_by_sha = {str(entry["image_sha256"]): entry for entry in entries}
    pages_by_sha = {str(page["image_sha256"]): page for page in pages}
    annotation_errors = []
    term_results = []
    distinct_terms: set[str] = set()
    expected_occurrences = matched_occurrences = 0
    for annotation in policy["proper_nouns"]:
        image_sha256 = str(annotation["image_sha256"])
        entry = entries_by_sha.get(image_sha256)
        page = pages_by_sha.get(image_sha256)
        if entry is None or page is None:
            annotation_errors.append(
                {"image_sha256": image_sha256, "reason": "verified image missing"}
            )
            continue
        reference_text = str(entry["reference_text"])
        hypothesis = str(page["hypothesis"])
        for term_value in annotation["terms"]:
            term = str(term_value)
            distinct_terms.add(term)
            expected = reference_text.count(term)
            if expected == 0:
                annotation_errors.append(
                    {
                        "image_sha256": image_sha256,
                        "term": term,
                        "reason": "term missing from reference",
                    }
                )
                continue
            actual = hypothesis.count(term)
            matched = min(expected, actual)
            expected_occurrences += expected
            matched_occurrences += matched
            term_results.append(
                {
                    "entry_id": int(entry["id"]),
                    "image_sha256": image_sha256,
                    "term": term,
                    "expected_occurrences": expected,
                    "actual_occurrences": actual,
                    "matched_occurrences": matched,
                    "missing_occurrences": expected - matched,
                }
            )
    checks.append(
        _check(
            "corpus.proper_noun_annotations_resolved",
            len(annotation_errors),
            0,
            not annotation_errors,
            errors=annotation_errors,
        )
    )
    checks.append(
        _check(
            "corpus.proper_noun_distinct_terms_min",
            len(distinct_terms),
            int(quality_policy["min_proper_noun_terms"]),
            len(distinct_terms) >= int(quality_policy["min_proper_noun_terms"]),
        )
    )
    checks.append(
        _check(
            "corpus.proper_noun_expected_occurrences_min",
            expected_occurrences,
            int(quality_policy["min_proper_noun_expected_occurrences"]),
            expected_occurrences
            >= int(quality_policy["min_proper_noun_expected_occurrences"]),
        )
    )
    proper_noun_recall = (
        matched_occurrences / expected_occurrences if expected_occurrences else None
    )
    missing_occurrences = expected_occurrences - matched_occurrences
    missing_terms = [result for result in term_results if result["missing_occurrences"]]
    checks.append(
        _check(
            "quality.proper_noun.recall_min",
            proper_noun_recall,
            float(quality_policy["proper_noun_recall_min"]),
            proper_noun_recall is not None
            and proper_noun_recall >= float(quality_policy["proper_noun_recall_min"]),
            missing_terms=missing_terms,
        )
    )
    checks.append(
        _check(
            "quality.proper_noun.missing_occurrences_max",
            missing_occurrences,
            int(quality_policy["proper_noun_missing_occurrences_max"]),
            missing_occurrences
            <= int(quality_policy["proper_noun_missing_occurrences_max"]),
            missing_terms=missing_terms,
        )
    )
    return {
        "policy_name": str(policy["name"]),
        "policy_schema_version": int(policy["schema_version"]),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "proper_noun_terms": term_results,
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
                f"  {status} {check['name']}: actual={check['actual']}, threshold={check['threshold']}"
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=("current", "tesseract", "yomitoku"))
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tesseract", type=Path)
    parser.add_argument("--tessdata-dir", type=Path)
    parser.add_argument("--ocr-python", type=Path)
    parser.add_argument("--ocr-path", type=Path)
    parser.add_argument("--corpus-json", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--fail-on-gate", action="store_true")
    args = parser.parse_args(argv)

    corpus = (
        json.loads(args.corpus_json.read_text(encoding="utf-8"))
        if args.corpus_json is not None
        else _get_json(f"{args.api_base.rstrip('/')}/api/ocr/ground-truth")
    )
    entries = [entry for entry in corpus["entries"] if entry["state"] == "verified"]
    if not entries:
        raise RuntimeError("verified ground-truth corpus is empty")

    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="pic2pdf-ocr-benchmark-") as temp_dir:
        work_dir = Path(temp_dir)
        if args.engine == "current":
            hypotheses = {int(entry["id"]): str(entry["ocr_text"]) for entry in entries}
        else:
            image_paths = _download_images(entries, args.api_base, work_dir)
            if args.engine == "tesseract":
                if args.tesseract is None or args.tessdata_dir is None:
                    parser.error("tesseract requires --tesseract and --tessdata-dir")
                hypotheses = _run_tesseract(
                    entries, image_paths, args.tesseract, args.tessdata_dir
                )
            else:
                if args.ocr_python is None or args.ocr_path is None:
                    parser.error("yomitoku requires --ocr-python and --ocr-path")
                hypotheses = _run_yomitoku(
                    entries,
                    image_paths,
                    args.ocr_python,
                    args.ocr_path,
                    repo_root,
                    work_dir,
                )

    report = summarize(entries, hypotheses, args.engine)
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    report["quality_gate"] = evaluate_quality_gate(corpus, report, policy)
    _print_summary(report)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 1 if args.fail_on_gate and not report["quality_gate"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
