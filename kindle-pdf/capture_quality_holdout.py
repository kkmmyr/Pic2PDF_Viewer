"""Read-only holdout evaluator for Kindle capture quality findings."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from capture_quality import CaptureQualityError, audit_capture_images

MANIFEST_SCHEMA_VERSION = "kindle-capture-quality-holdout-v1"


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_case_dir(image_root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError("holdout image_dir must be a non-empty relative path")
    root = image_root.resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("holdout image_dir escapes image root")
    if not resolved.is_dir():
        raise ValueError(f"holdout image_dir is missing: {relative}")
    return resolved


def _capture_image_paths(case_dir: Path, expected_count: int) -> list[Path]:
    paths = [case_dir / f"{index:03}.png" for index in range(1, expected_count + 1)]
    if any(not path.is_file() for path in paths):
        raise ValueError(f"holdout images are incomplete: {case_dir}")
    return paths


def build_holdout_manifest(
    spec: Mapping[str, Any], *, image_root: Path
) -> dict[str, Any]:
    source_cases = spec.get("cases")
    if not isinstance(source_cases, list) or not source_cases:
        raise ValueError("holdout cases must be a non-empty array")
    cases = []
    for source_case in source_cases:
        if not isinstance(source_case, Mapping):
            raise ValueError("holdout case must be an object")
        image_dir = str(source_case["image_dir"])
        expected_count = int(source_case["expected_count"])
        paths = _capture_image_paths(
            _resolve_case_dir(image_root, image_dir), expected_count
        )
        cases.append(
            {
                "case_id": str(source_case["case_id"]),
                "source": str(source_case["source"]),
                "image_dir": image_dir,
                "expected_count": expected_count,
                "images": [
                    {"name": path.name, "sha256": _file_sha256(path)} for path in paths
                ],
                "labels": [
                    {
                        "code": str(label["code"]),
                        "files": sorted(str(name) for name in label.get("files", [])),
                    }
                    for label in source_case.get("labels", [])
                ],
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "holdout_id": str(spec["holdout_id"]),
        "cases": cases,
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def _verify_manifest(manifest: Mapping[str, Any], image_root: Path) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported capture quality holdout schema")
    content = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    if manifest.get("manifest_sha256") != _canonical_sha256(content):
        raise ValueError("capture quality holdout manifest digest mismatch")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("capture quality holdout cases are missing")
    seen_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("capture quality holdout case must be an object")
        case_id = str(case["case_id"])
        if case_id in seen_ids:
            raise ValueError(f"duplicate capture quality case: {case_id}")
        seen_ids.add(case_id)
        case_dir = _resolve_case_dir(image_root, str(case["image_dir"]))
        images = case.get("images")
        if not isinstance(images, list) or len(images) != int(case["expected_count"]):
            raise ValueError(f"capture quality image inventory mismatch: {case_id}")
        for image in images:
            path = case_dir / str(image["name"])
            if not path.is_file() or image.get("sha256") != _file_sha256(path):
                raise ValueError(
                    f"capture quality image digest mismatch: {case_id}/{path.name}"
                )


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


def evaluate_holdout_manifest(
    manifest: Mapping[str, Any],
    *,
    image_root: Path,
) -> dict[str, Any]:
    _verify_manifest(manifest, image_root)
    expected_keys: set[tuple[str, str, tuple[str, ...]]] = set()
    predicted_keys: set[tuple[str, str, tuple[str, ...]]] = set()
    case_reports = []
    policy_versions: set[tuple[str, str, str]] = set()
    image_count = 0
    for case in manifest["cases"]:
        case_id = str(case["case_id"])
        expected = {_finding_key(case_id, label) for label in case.get("labels", [])}
        expected_keys.update(expected)
        case_dir = _resolve_case_dir(image_root, str(case["image_dir"]))
        try:
            result = audit_capture_images(
                case_dir,
                expected_count=int(case["expected_count"]),
                source=str(case["source"]),
            )
            findings = list(result.findings)
            result_manifest = result.to_manifest()
            policy_versions.add(
                (
                    str(result_manifest["policy_version"]),
                    str(result_manifest["warning_policy_version"]),
                    str(result_manifest["overlay_detector"]["policy_version"]),
                )
            )
            error = None
        except CaptureQualityError as exc:
            findings = []
            error = str(exc)
            if error.startswith("repeated_screen_overlay_detected:"):
                names = error.split("files=", 1)[1].split(", bounds=", 1)[0].split(",")
                findings.append(
                    {
                        "code": "repeated_screen_overlay_detected",
                        "files": names,
                    }
                )
        predicted = {_finding_key(case_id, finding) for finding in findings}
        predicted_keys.update(predicted)
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
                "precision": _safe_ratio(true_positive, true_positive + false_positive),
                "recall": _safe_ratio(true_positive, true_positive + false_negative),
            }
        )
    return {
        "schema_version": "kindle-capture-quality-report-v1",
        "holdout_id": manifest["holdout_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "case_count": len(manifest["cases"]),
        "image_count": image_count,
        "policy_versions": [list(item) for item in sorted(policy_versions)],
        "metrics": metrics,
        "cases": case_reports,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = evaluate_holdout_manifest(manifest, image_root=args.image_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(f"cases={report['case_count']}, images={report['image_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
