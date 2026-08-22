"""Integrity contract for private Kindle capture-quality holdouts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = "kindle-capture-quality-holdout-v1"
_ALLOWED_SOURCES = frozenset({"comic", "novel"})
_SINGLE_FILE_LABEL_CODES = frozenset(
    {
        "blank_or_sparse_candidate",
        "low_size_candidate",
        "novel_edge_content_candidate",
    }
)
_PAIR_LABEL_CODES = frozenset({"adjacent_near_duplicate_candidate"})
_MULTI_FILE_LABEL_CODES = frozenset(
    {
        "exact_duplicate_candidate",
        "repeated_screen_overlay_candidate",
        "repeated_screen_overlay_detected",
        "transient_bottom_right_overlay_candidate",
    }
)
_ALLOWED_LABEL_CODES = (
    _SINGLE_FILE_LABEL_CODES | _PAIR_LABEL_CODES | _MULTI_FILE_LABEL_CODES
)
_DATASET_ROLES = frozenset({"real_image_holdout", "controlled_corruption"})
_GROUND_TRUTH_KINDS = frozenset(
    {"human_labels", "ai_visual_labels", "deterministic_corruption"}
)
_HUMAN_CONFIRMATION_STATES = frozenset({"confirmed", "pending", "not_applicable"})
_PROVENANCE_DIGEST_FIELDS = (
    "selection_manifest_sha256",
    "label_manifest_sha256",
    "corruption_recipe_sha256",
)
_PROVENANCE_OPTIONAL_STRING_FIELDS = ("reviewed_at",)
_PROVENANCE_FIELDS = frozenset(
    {
        "dataset_role",
        "ground_truth_kind",
        "reviewer_kind",
        "human_confirmation",
        *_PROVENANCE_DIGEST_FIELDS,
        *_PROVENANCE_OPTIONAL_STRING_FIELDS,
    }
)


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


def resolve_case_dir(image_root: Path, relative: str) -> Path:
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
    if expected_count <= 0:
        raise ValueError("holdout expected_count must be a positive integer")
    paths = [case_dir / f"{index:03}.png" for index in range(1, expected_count + 1)]
    expected_names = {path.name for path in paths}
    unexpected = sorted(
        path.name
        for path in case_dir.iterdir()
        if path.is_symlink() or not path.is_file() or path.name not in expected_names
    )
    if unexpected:
        raise ValueError(
            f"holdout image directory has unexpected entries: {case_dir}: "
            + ", ".join(unexpected)
        )
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise ValueError(f"holdout images are incomplete: {case_dir}")
    return paths


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"capture quality {field} must be a non-empty string")
    return value


def _positive_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("holdout expected_count must be a positive integer")
    return value


def _source(value: Any) -> str:
    source = _required_string(value, "source")
    if source not in _ALLOWED_SOURCES:
        raise ValueError(f"unsupported capture quality source: {source}")
    return source


def _validate_provenance_relationships(
    dataset_role: str,
    ground_truth_kind: str,
    human_confirmation: str,
) -> None:
    if dataset_role == "controlled_corruption" and (
        ground_truth_kind != "deterministic_corruption"
        or human_confirmation != "not_applicable"
    ):
        raise ValueError(
            "controlled corruption requires deterministic ground truth and "
            "not_applicable human confirmation"
        )
    if (
        dataset_role != "controlled_corruption"
        and ground_truth_kind == "deterministic_corruption"
    ):
        raise ValueError(
            "deterministic corruption ground truth requires controlled dataset role"
        )
    if ground_truth_kind == "human_labels" and human_confirmation != "confirmed":
        raise ValueError("human labels require confirmed human confirmation")


def _provenance_required(value: Mapping) -> dict[str, str]:
    dataset_role = _required_string(value.get("dataset_role"), "dataset role")
    if dataset_role not in _DATASET_ROLES:
        raise ValueError(f"unsupported capture quality dataset role: {dataset_role}")
    ground_truth_kind = _required_string(
        value.get("ground_truth_kind"), "ground truth kind"
    )
    if ground_truth_kind not in _GROUND_TRUTH_KINDS:
        raise ValueError(
            f"unsupported capture quality ground truth kind: {ground_truth_kind}"
        )
    reviewer_kind = _required_string(value.get("reviewer_kind"), "reviewer kind")
    human_confirmation = _required_string(
        value.get("human_confirmation"), "human confirmation"
    )
    if human_confirmation not in _HUMAN_CONFIRMATION_STATES:
        raise ValueError(
            "unsupported capture quality human confirmation state: "
            f"{human_confirmation}"
        )
    _validate_provenance_relationships(
        dataset_role,
        ground_truth_kind,
        human_confirmation,
    )
    return {
        "dataset_role": dataset_role,
        "ground_truth_kind": ground_truth_kind,
        "reviewer_kind": reviewer_kind,
        "human_confirmation": human_confirmation,
    }


def _provenance_digest(value: Any, field: str) -> str:
    digest = _required_string(value, field)
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"capture quality provenance digest is invalid: {field}")
    return digest


def _provenance(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("capture quality provenance must be an object")
    unknown = sorted(str(field) for field in value if field not in _PROVENANCE_FIELDS)
    if unknown:
        raise ValueError(f"unsupported capture quality provenance field: {unknown[0]}")
    normalized = _provenance_required(value)
    for field in _PROVENANCE_DIGEST_FIELDS:
        if field in value:
            normalized[field] = _provenance_digest(value.get(field), field)
    for field in _PROVENANCE_OPTIONAL_STRING_FIELDS:
        if field in value:
            normalized[field] = _required_string(value.get(field), field)
    return normalized


def _label_files(
    value: Any,
    *,
    image_names: set[str],
    case_id: str,
    code: str,
) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(name, str) for name in value)
    ):
        raise ValueError(f"capture quality label files are invalid: {case_id}/{code}")
    sorted_files = sorted(value)
    if len(set(sorted_files)) != len(sorted_files):
        raise ValueError(f"duplicate capture quality label file: {case_id}/{code}")
    unknown = [name for name in sorted_files if name not in image_names]
    if unknown:
        raise ValueError(
            f"label file is not in image inventory: {case_id}/{unknown[0]}"
        )
    return sorted_files


def _validate_label_arity(code: str, files: list[str], case_id: str) -> None:
    if code in _SINGLE_FILE_LABEL_CODES and len(files) != 1:
        raise ValueError(f"capture quality label requires one file: {case_id}/{code}")
    if code in _PAIR_LABEL_CODES and len(files) != 2:
        raise ValueError(f"capture quality label requires two files: {case_id}/{code}")
    if code in _MULTI_FILE_LABEL_CODES and len(files) < 2:
        raise ValueError(
            f"capture quality label requires multiple files: {case_id}/{code}"
        )


def _labels(
    value: Any,
    *,
    image_names: set[str],
    case_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"capture quality labels must be an array: {case_id}")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for label in value:
        if not isinstance(label, Mapping):
            raise ValueError(f"capture quality label must be an object: {case_id}")
        code = _required_string(label.get("code"), "label code")
        if code not in _ALLOWED_LABEL_CODES:
            raise ValueError(f"unsupported capture quality label code: {code}")
        files = _label_files(
            label.get("files"),
            image_names=image_names,
            case_id=case_id,
            code=code,
        )
        _validate_label_arity(code, files, case_id)
        key = (code, tuple(files))
        if key in seen:
            raise ValueError(f"duplicate capture quality label: {case_id}/{code}")
        seen.add(key)
        normalized.append({"code": code, "files": files})
    return normalized


def _build_case(source_case: Mapping[str, Any], image_root: Path) -> dict[str, Any]:
    case_id = _required_string(source_case.get("case_id"), "case ID")
    source = _source(source_case.get("source"))
    image_dir = _required_string(source_case.get("image_dir"), "image_dir")
    expected_count = _positive_int(source_case.get("expected_count"))
    paths = _capture_image_paths(
        resolve_case_dir(image_root, image_dir),
        expected_count,
    )
    labels = _labels(
        source_case.get("labels", []),
        image_names={path.name for path in paths},
        case_id=case_id,
    )
    return {
        "case_id": case_id,
        "source": source,
        "image_dir": image_dir,
        "expected_count": expected_count,
        "images": [{"name": path.name, "sha256": _file_sha256(path)} for path in paths],
        "labels": labels,
    }


def build_holdout_manifest(
    spec: Mapping[str, Any], *, image_root: Path
) -> dict[str, Any]:
    holdout_id = _required_string(spec.get("holdout_id"), "holdout ID")
    provenance = _provenance(spec.get("provenance"))
    source_cases = spec.get("cases")
    if not isinstance(source_cases, list) or not source_cases:
        raise ValueError("holdout cases must be a non-empty array")
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for source_case in source_cases:
        if not isinstance(source_case, Mapping):
            raise ValueError("holdout case must be an object")
        case = _build_case(source_case, image_root)
        if case["case_id"] in seen_ids:
            raise ValueError(f"duplicate capture quality case: {case['case_id']}")
        seen_ids.add(case["case_id"])
        cases.append(case)
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "holdout_id": holdout_id,
        "cases": cases,
    }
    if provenance is not None:
        manifest["provenance"] = provenance
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def _verify_images(
    images: Any,
    paths: list[Path],
    case_id: str,
) -> None:
    if not isinstance(images, list) or len(images) != len(paths):
        raise ValueError(f"capture quality image inventory mismatch: {case_id}")
    for image, path in zip(images, paths, strict=True):
        if not isinstance(image, Mapping) or image.get("name") != path.name:
            raise ValueError(f"capture quality image inventory mismatch: {case_id}")
        if image.get("sha256") != _file_sha256(path):
            raise ValueError(
                f"capture quality image digest mismatch: {case_id}/{path.name}"
            )


def _verify_case(case: Mapping[str, Any], image_root: Path) -> str:
    case_id = _required_string(case.get("case_id"), "case ID")
    _source(case.get("source"))
    image_dir = _required_string(case.get("image_dir"), "image_dir")
    expected_count = _positive_int(case.get("expected_count"))
    paths = _capture_image_paths(
        resolve_case_dir(image_root, image_dir),
        expected_count,
    )
    _verify_images(case.get("images"), paths, case_id)
    normalized_labels = _labels(
        case.get("labels", []),
        image_names={path.name for path in paths},
        case_id=case_id,
    )
    if case.get("labels", []) != normalized_labels:
        raise ValueError(f"capture quality labels are not canonical: {case_id}")
    return case_id


def verify_holdout_manifest(manifest: Mapping[str, Any], image_root: Path) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported capture quality holdout schema")
    content = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    if manifest.get("manifest_sha256") != _canonical_sha256(content):
        raise ValueError("capture quality holdout manifest digest mismatch")
    _required_string(manifest.get("holdout_id"), "holdout ID")
    provenance = _provenance(manifest.get("provenance"))
    if "provenance" in manifest and (
        provenance is None or manifest.get("provenance") != provenance
    ):
        raise ValueError("capture quality provenance is not canonical")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("capture quality holdout cases are missing")
    seen_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("capture quality holdout case must be an object")
        case_id = _verify_case(case, image_root)
        if case_id in seen_ids:
            raise ValueError(f"duplicate capture quality case: {case_id}")
        seen_ids.add(case_id)
