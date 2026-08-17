"""Fail-closed B-35 formal holdout manifest and one-time opening ledger."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ocr_holdout_ledger import open_formal_holdout

MANIFEST_SCHEMA_VERSION = "b35-holdout-v1"


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _without_manifest_digest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key != "manifest_sha256"}


def _resolve_package(package_root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError("qa_package must be a non-empty relative path")
    root = package_root.resolve()
    resolved = (root / relative_path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("qa_package escapes package root")
    if not resolved.is_file():
        raise ValueError(f"QA package is missing: {relative_path}")
    return resolved


def _corpus_by_id(corpus: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        raise ValueError("corpus entries must be an array")
    result: dict[int, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("corpus entry must be an object")
        entry_id = int(entry["id"])
        if entry_id in result:
            raise ValueError(f"duplicate corpus entry: {entry_id}")
        result[entry_id] = entry
    return result


def _selection_output_sha256(entries: Sequence[Mapping[str, Any]]) -> str:
    identities = [
        {
            "entry_id": int(entry["entry_id"]),
            "run_id": int(entry["run_id"]),
            "page_no": int(entry["page_no"]),
            "series_id": str(entry["series_id"]),
            "image_sha256": str(entry["image_sha256"]),
        }
        for entry in entries
    ]
    return canonical_sha256(sorted(identities, key=lambda item: item["entry_id"]))


def build_formal_manifest(
    spec: Mapping[str, Any],
    corpus: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    package_root: Path,
    sealed_at: str,
) -> dict[str, Any]:
    source_entries = spec.get("entries")
    if not isinstance(source_entries, list) or not source_entries:
        raise ValueError("holdout spec entries must be a non-empty array")
    corpus_entries = _corpus_by_id(corpus)
    entries = []
    for source in source_entries:
        if not isinstance(source, Mapping):
            raise ValueError("holdout spec entry must be an object")
        entry_id = int(source["entry_id"])
        corpus_entry = corpus_entries.get(entry_id)
        if corpus_entry is None:
            raise ValueError(f"verified ground-truth entry is missing: {entry_id}")
        package_name = str(source["qa_package"])
        package_path = _resolve_package(package_root, package_name)
        entries.append(
            {
                "entry_id": entry_id,
                "run_id": int(source["run_id"]),
                "page_no": int(source["page_no"]),
                "series_id": str(source["series_id"]),
                "image_sha256": str(corpus_entry["image_sha256"]),
                "page_type": str(corpus_entry["page_type"]),
                "layout_type": str(corpus_entry.get("layout_type", "unknown")),
                "reference_sha256": hashlib.sha256(
                    str(corpus_entry["reference_text"]).encode("utf-8")
                ).hexdigest(),
                "qa_package": package_name,
                "qa_package_sha256": file_sha256(package_path),
                "proper_nouns": [str(term) for term in source.get("proper_nouns", [])],
            }
        )
    entries.sort(key=lambda item: item["entry_id"])
    selection = spec.get("selection")
    if not isinstance(selection, Mapping):
        raise ValueError("holdout selection must be an object")
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "holdout_id": str(spec["holdout_id"]),
        "purpose": str(spec["purpose"]),
        "state": "sealed",
        "sealed_at": sealed_at,
        "selection": {
            "method": str(selection["method"]),
            "input_sha256": str(selection["input_sha256"]),
            "output_sha256": _selection_output_sha256(entries),
        },
        "policy_sha256": canonical_sha256(policy),
        "entries": entries,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    verify_formal_manifest(manifest, corpus, policy, package_root=package_root)
    return manifest


def _verify_manifest_identity(
    manifest: Mapping[str, Any], policy: Mapping[str, Any]
) -> tuple[str, Mapping[str, Any], list[Any]]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported formal holdout manifest schema")
    if manifest.get("purpose") != "b35_final" or manifest.get("state") != "sealed":
        raise ValueError("formal holdout must be sealed for b35_final")
    expected_manifest_sha = canonical_sha256(_without_manifest_digest(manifest))
    if manifest.get("manifest_sha256") != expected_manifest_sha:
        raise ValueError("formal holdout manifest digest mismatch")
    if manifest.get("policy_sha256") != canonical_sha256(policy):
        raise ValueError("formal holdout policy digest mismatch")
    selection = manifest.get("selection")
    if not isinstance(selection, Mapping) or selection.get("method") != "quality_blind":
        raise ValueError("formal holdout selection must be quality_blind")
    if len(str(selection.get("input_sha256") or "")) != 64:
        raise ValueError("formal holdout selection input digest is invalid")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("formal holdout entries must be a non-empty array")
    if selection.get("output_sha256") != _selection_output_sha256(entries):
        raise ValueError("formal holdout selection output digest mismatch")
    return expected_manifest_sha, selection, entries


def _verify_formal_entry(
    entry: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    package_root: Path,
) -> tuple[str, bool, set[str], int]:
    entry_id = int(entry["entry_id"])
    for key in ("run_id", "page_no"):
        if int(entry[key]) != int(source[key]):
            raise ValueError(f"formal holdout {key} mismatch: {entry_id}")
    if entry["image_sha256"] != source["image_sha256"]:
        raise ValueError(f"formal holdout image digest mismatch: {entry_id}")
    reference_text = str(source["reference_text"])
    reference_sha = hashlib.sha256(reference_text.encode("utf-8")).hexdigest()
    if entry["reference_sha256"] != reference_sha:
        raise ValueError(f"formal holdout reference digest mismatch: {entry_id}")
    package_path = _resolve_package(package_root, str(entry["qa_package"]))
    if entry["qa_package_sha256"] != file_sha256(package_path):
        raise ValueError(f"formal holdout package digest mismatch: {entry_id}")
    is_normal_prose = (
        entry.get("page_type") == "narrative"
        and entry.get("layout_type") == "normal_prose"
    )
    terms = {str(term) for term in entry.get("proper_nouns", [])}
    occurrences = sum(reference_text.count(term) for term in terms)
    return str(entry["series_id"]), is_normal_prose, terms, occurrences


def verify_formal_manifest(
    manifest: Mapping[str, Any],
    corpus: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    package_root: Path,
) -> dict[str, Any]:
    expected_manifest_sha, _, entries = _verify_manifest_identity(manifest, policy)

    corpus_entries = _corpus_by_id(corpus)
    seen_ids: set[int] = set()
    series: set[str] = set()
    normal_prose_count = 0
    distinct_terms: set[str] = set()
    expected_occurrences = 0
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("formal holdout entry must be an object")
        entry_id = int(entry["entry_id"])
        if entry_id in seen_ids:
            raise ValueError(f"duplicate formal holdout entry: {entry_id}")
        seen_ids.add(entry_id)
        source = corpus_entries.get(entry_id)
        if source is None or source.get("state") != "verified":
            raise ValueError(f"verified ground-truth entry is missing: {entry_id}")
        series_id, is_normal_prose, terms, occurrences = _verify_formal_entry(
            entry, source, package_root=package_root
        )
        series.add(series_id)
        normal_prose_count += int(is_normal_prose)
        distinct_terms.update(terms)
        expected_occurrences += occurrences

    minimum_terms = int(policy["quality"]["min_proper_noun_terms"])
    minimum_occurrences = int(policy["quality"]["min_proper_noun_expected_occurrences"])
    if len(series) < 3:
        raise ValueError("formal holdout requires at least 3 series")
    if normal_prose_count < 20:
        raise ValueError("formal holdout requires at least 20 normal prose pages")
    if len(distinct_terms) < minimum_terms:
        raise ValueError("formal holdout has too few proper noun terms")
    if expected_occurrences < minimum_occurrences:
        raise ValueError("formal holdout has too few proper noun occurrences")
    return {
        "manifest_sha256": expected_manifest_sha,
        "entry_count": len(entries),
        "series_count": len(series),
        "normal_prose_count": normal_prose_count,
        "proper_noun_terms": len(distinct_terms),
        "proper_noun_expected_occurrences": expected_occurrences,
    }


def build_formal_gate_policy(
    manifest: Mapping[str, Any], policy: Mapping[str, Any]
) -> dict[str, Any]:
    """Scope generic gate configuration to the sealed formal holdout contract."""
    effective = deepcopy(dict(policy))
    corpus_policy = effective.get("corpus")
    if not isinstance(corpus_policy, dict):
        raise ValueError("formal holdout policy corpus must be an object")
    corpus_policy["min_page_type_counts"] = {}
    corpus_policy["min_layout_type_counts"] = {}

    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("formal holdout entries must be an array")
    effective["proper_nouns"] = [
        {
            "image_sha256": str(entry["image_sha256"]),
            "terms": [str(term) for term in entry.get("proper_nouns", [])],
        }
        for entry in entries
        if isinstance(entry, Mapping) and entry.get("proper_nouns")
    ]
    return effective


def authorize_formal_holdout_open(
    manifest: Mapping[str, Any],
    corpus: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    package_root: Path,
    ledger_path: Path,
    operator: str,
    reason: str,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    verified = verify_formal_manifest(
        manifest, corpus, policy, package_root=package_root
    )
    if not operator.strip() or not reason.strip():
        raise ValueError("formal holdout opening requires operator and reason")
    open_formal_holdout(
        ledger_path,
        str(verified["manifest_sha256"]),
        operator=operator,
        reason=reason,
        occurred_at=occurred_at,
    )
    return verified
