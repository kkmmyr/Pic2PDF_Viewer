"""OCR benchmark quality-policy evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median
from typing import Any

from ocr_benchmark_engines import _is_truthy
from ocr_benchmark_text import _normalize_text


def column_gap_diagnostic(
    segments: Sequence[dict[str, Any]], policy: dict[str, Any]
) -> dict[str, Any]:
    """Detect an omitted interior vertical column from NDLOCR bbox spacing."""
    columns: list[tuple[float, int]] = []
    for segment in segments:
        if not _is_truthy(segment.get("is_vertical")):
            continue
        bbox = segment.get("bbox")
        if not isinstance(bbox, list):
            continue
        x_coordinates = [
            float(point[0])
            for point in bbox
            if isinstance(point, list) and point and isinstance(point[0], (int, float))
        ]
        if not x_coordinates:
            continue
        columns.append(
            (
                sum(x_coordinates) / len(x_coordinates),
                len(_normalize_text(str(segment.get("text", "")))),
            )
        )
    columns.sort(reverse=True)
    if len(columns) < 4:
        return {"geometry_available": False, "vertical_columns": len(columns)}

    gaps = [
        columns[index][0] - columns[index + 1][0]
        for index in range(len(columns) - 1)
        if columns[index][0] > columns[index + 1][0]
    ]
    if len(gaps) < 3:
        return {"geometry_available": False, "vertical_columns": len(columns)}

    max_rightmost_header_chars = int(policy.get("max_rightmost_header_chars", 20))
    candidate_gaps = gaps[1:] if columns[0][1] <= max_rightmost_header_chars else gaps
    if not candidate_gaps:
        return {"geometry_available": False, "vertical_columns": len(columns)}
    median_gap = float(median(gaps))
    if median_gap <= 0:
        return {"geometry_available": False, "vertical_columns": len(columns)}
    max_gap = max(candidate_gaps)
    return {
        "geometry_available": True,
        "vertical_columns": len(columns),
        "median_column_gap": median_gap,
        "max_interior_column_gap": max_gap,
        "max_interior_gap_ratio": max_gap / median_gap,
        "ignored_rightmost_header_gap": len(candidate_gaps) != len(gaps),
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


def _evaluate_corpus_checks(
    entries: list[dict[str, Any]], corpus_policy: dict[str, Any]
) -> list[dict[str, Any]]:
    checks = []
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
    return checks


def _evaluate_cer_checks(
    pages: list[dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
    quality_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    checks = []
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
    return checks


def _evaluate_omission_check(
    pages: list[dict[str, Any]], omission_policy: dict[str, Any]
) -> dict[str, Any]:
    suspects = []
    min_gap_ratio = float(omission_policy.get("min_interior_column_gap_ratio", 1.6))
    for page in pages:
        deletion_suspect = (
            page["page_type"] == omission_policy["page_type"]
            and int(page["deletions"]) >= int(omission_policy["min_deleted_chars"])
            and page["deletion_rate"] is not None
            and float(page["deletion_rate"])
            >= float(omission_policy["min_deletion_rate"])
        )
        if not deletion_suspect:
            continue
        geometry = column_gap_diagnostic(page.get("segments", []), omission_policy)
        if geometry["geometry_available"] and (
            float(geometry["max_interior_gap_ratio"]) < min_gap_ratio
        ):
            continue
        suspects.append(
            {
                "entry_id": int(page["entry_id"]),
                "run_id": int(page["run_id"]),
                "page_no": int(page["page_no"]),
                "deletions": int(page["deletions"]),
                "deletion_rate": page["deletion_rate"],
                **geometry,
            }
        )
    maximum = int(omission_policy["max_suspect_pages"])
    return _check(
        "quality.column_omission.suspect_pages_max",
        len(suspects),
        maximum,
        len(suspects) <= maximum,
        suspects=suspects,
    )


def _evaluate_proper_nouns(
    entries: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    quality_policy = policy["quality"]
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

    proper_noun_recall = (
        matched_occurrences / expected_occurrences if expected_occurrences else None
    )
    missing_occurrences = expected_occurrences - matched_occurrences
    missing_terms = [result for result in term_results if result["missing_occurrences"]]
    checks = [
        _check(
            "corpus.proper_noun_annotations_resolved",
            len(annotation_errors),
            0,
            not annotation_errors,
            errors=annotation_errors,
        ),
        _check(
            "corpus.proper_noun_distinct_terms_min",
            len(distinct_terms),
            int(quality_policy["min_proper_noun_terms"]),
            len(distinct_terms) >= int(quality_policy["min_proper_noun_terms"]),
        ),
        _check(
            "corpus.proper_noun_expected_occurrences_min",
            expected_occurrences,
            int(quality_policy["min_proper_noun_expected_occurrences"]),
            expected_occurrences
            >= int(quality_policy["min_proper_noun_expected_occurrences"]),
        ),
        _check(
            "quality.proper_noun.recall_min",
            proper_noun_recall,
            float(quality_policy["proper_noun_recall_min"]),
            proper_noun_recall is not None
            and proper_noun_recall >= float(quality_policy["proper_noun_recall_min"]),
            missing_terms=missing_terms,
        ),
        _check(
            "quality.proper_noun.missing_occurrences_max",
            missing_occurrences,
            int(quality_policy["proper_noun_missing_occurrences_max"]),
            missing_occurrences
            <= int(quality_policy["proper_noun_missing_occurrences_max"]),
            missing_terms=missing_terms,
        ),
    ]
    return checks, term_results


def evaluate_quality_gate(
    corpus: dict[str, Any], report: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    if int(policy.get("schema_version", 0)) != 1:
        raise ValueError("unsupported OCR quality policy schema_version")
    entries = [entry for entry in corpus["entries"] if entry["state"] == "verified"]
    pages = report["pages"]
    metrics = {metric["group"]: metric for metric in report["metrics"]}
    quality_policy = policy["quality"]

    checks = _evaluate_corpus_checks(entries, policy["corpus"])
    checks.extend(_evaluate_cer_checks(pages, metrics, quality_policy))
    checks.append(_evaluate_omission_check(pages, quality_policy["column_omission"]))
    proper_noun_checks, term_results = _evaluate_proper_nouns(entries, pages, policy)
    checks.extend(proper_noun_checks)
    return {
        "policy_name": str(policy["name"]),
        "policy_schema_version": int(policy["schema_version"]),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "proper_noun_terms": term_results,
    }
