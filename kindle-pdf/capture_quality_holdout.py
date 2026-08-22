"""Read-only holdout evaluator for Kindle capture quality findings."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from capture_quality import CaptureQualityError, audit_capture_images
from capture_quality_holdout_contract import (
    MANIFEST_SCHEMA_VERSION,
    _canonical_sha256,
    build_holdout_manifest,
    resolve_case_dir,
    verify_holdout_manifest,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "_canonical_sha256",
    "build_holdout_manifest",
    "evaluate_holdout_manifest",
    "main",
]


def _finding_key(
    case_id: str, finding: Mapping[str, Any]
) -> tuple[str, str, tuple[str, ...]]:
    return (
        case_id,
        str(finding["code"]),
        tuple(sorted(str(name) for name in finding.get("files", []))),
    )


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _blocking_overlay_finding(error: str, case_id: str) -> dict[str, Any]:
    if "files=" not in error or ", bounds=" not in error:
        raise ValueError(f"capture quality blocking finding is malformed: {case_id}")
    files = error.split("files=", 1)[1].split(", bounds=", 1)[0].split(",")
    if not files or any(not name for name in files):
        raise ValueError(f"capture quality blocking finding is malformed: {case_id}")
    return {"code": "repeated_screen_overlay_detected", "files": files}


def _audit_case(
    case: Mapping[str, Any], image_root: Path
) -> tuple[list[dict], str | None, tuple[str, str, str]]:
    case_id = str(case["case_id"])
    case_dir = resolve_case_dir(image_root, str(case["image_dir"]))
    try:
        result = audit_capture_images(
            case_dir,
            expected_count=int(case["expected_count"]),
            source=str(case["source"]),
        )
    except CaptureQualityError as exc:
        error = str(exc)
        if not error.startswith("repeated_screen_overlay_detected:"):
            raise ValueError(
                f"capture quality holdout case is not auditable: {case_id}: {error}"
            ) from exc
        return (
            [_blocking_overlay_finding(error, case_id)],
            error,
            (
                "kindle-image-qa-v1",
                "kindle-image-warning-v2",
                "kindle-repeated-overlay-v2",
            ),
        )
    result_manifest = result.to_manifest()
    versions = (
        str(result_manifest["policy_version"]),
        str(result_manifest["warning_policy_version"]),
        str(result_manifest["overlay_detector"]["policy_version"]),
    )
    return list(result.findings), None, versions


def _code_metrics(
    expected_keys: set[tuple[str, str, tuple[str, ...]]],
    predicted_keys: set[tuple[str, str, tuple[str, ...]]],
) -> list[dict[str, Any]]:
    by_code: dict[str, dict[str, set]] = defaultdict(
        lambda: {"expected": set(), "predicted": set()}
    )
    for key in expected_keys:
        by_code[key[1]]["expected"].add(key)
    for key in predicted_keys:
        by_code[key[1]]["predicted"].add(key)
    metrics = []
    for code in sorted(by_code):
        expected = by_code[code]["expected"]
        predicted = by_code[code]["predicted"]
        true_positive = len(expected & predicted)
        false_positive = len(predicted - expected)
        false_negative = len(expected - predicted)
        metrics.append(
            {
                "code": code,
                "true_positive": true_positive,
                "false_positive": false_positive,
                "false_negative": false_negative,
                "precision": _safe_ratio(
                    true_positive,
                    true_positive + false_positive,
                ),
                "recall": _safe_ratio(
                    true_positive,
                    true_positive + false_negative,
                ),
            }
        )
    return metrics


def evaluate_holdout_manifest(
    manifest: Mapping[str, Any],
    *,
    image_root: Path,
) -> dict[str, Any]:
    verify_holdout_manifest(manifest, image_root)
    expected_keys: set[tuple[str, str, tuple[str, ...]]] = set()
    predicted_keys: set[tuple[str, str, tuple[str, ...]]] = set()
    case_reports = []
    policy_versions: set[tuple[str, str, str]] = set()
    image_count = 0
    for case in manifest["cases"]:
        case_id = str(case["case_id"])
        expected = {_finding_key(case_id, label) for label in case.get("labels", [])}
        findings, error, versions = _audit_case(case, image_root)
        predicted = {_finding_key(case_id, finding) for finding in findings}
        expected_keys.update(expected)
        predicted_keys.update(predicted)
        policy_versions.add(versions)
        image_count += int(case["expected_count"])
        case_reports.append(
            {
                "case_id": case_id,
                "expected": len(expected),
                "predicted": len(predicted),
                "error": error,
                "findings": findings,
            }
        )
    report = {
        "schema_version": "kindle-capture-quality-report-v1",
        "holdout_id": manifest["holdout_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "case_count": len(manifest["cases"]),
        "image_count": image_count,
        "policy_versions": [list(item) for item in sorted(policy_versions)],
        "metrics": _code_metrics(expected_keys, predicted_keys),
        "cases": case_reports,
    }
    if "provenance" in manifest:
        report["provenance"] = manifest["provenance"]
    return report


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_mapping(path: Path, label: str) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"capture quality holdout {label} must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build-spec", type=Path)
    mode.add_argument("--manifest", type=Path)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    if args.build_spec is not None:
        if args.manifest_output is None or args.output is not None:
            parser.error("build mode requires --manifest-output and forbids --output")
        spec = _load_mapping(args.build_spec, "spec")
        manifest = build_holdout_manifest(spec, image_root=args.image_root)
        _write_json_atomic(args.manifest_output, manifest)
        print(f"cases={len(manifest['cases'])}, manifest={manifest['manifest_sha256']}")
        return 0

    if args.output is None or args.manifest_output is not None:
        parser.error("evaluation mode requires --output and forbids --manifest-output")
    assert args.manifest is not None
    manifest = _load_mapping(args.manifest, "manifest")
    report = evaluate_holdout_manifest(manifest, image_root=args.image_root)
    _write_json_atomic(args.output, report)
    print(f"cases={report['case_count']}, images={report['image_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
