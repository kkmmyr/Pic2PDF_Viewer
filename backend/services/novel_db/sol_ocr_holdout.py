"""Fail-closed fresh formal holdouts for the Sol image-OCR campaign.

The selector deliberately consumes campaign metadata only.  It never opens an
image or reads OCR text / quality values, so the holdout remains quality blind
until it is opened through the one-time ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "sol-ocr-fresh-holdout-v1"
LEDGER_SCHEMA_VERSION = "sol-ocr-fresh-holdout-ledger-v1"
CAMPAIGN_SCHEMA_VERSION = "sol-ocr-campaign-v1"
PILOT_SCHEMA_VERSION = "sol-ocr-pilot-v1"
B35_SCHEMA_VERSION = "b35-holdout-v1"
SELECTION_POLICY = "central_60_percent_one_page_per_book_sha_rank_v1"


def canonical_sha256(value: object) -> str:
    """Return the SHA-256 of canonical JSON."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _require_sha256(value: object, label: str) -> str:
    if not _is_sha256(value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return str(value)


def _parse_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return value


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _verify_self_digest(value: Mapping[str, Any], digest_key: str, label: str) -> str:
    expected = _require_sha256(value.get(digest_key), f"{label} {digest_key}")
    actual = canonical_sha256({key: item for key, item in value.items() if key != digest_key})
    if actual != expected:
        raise ValueError(f"{label} digest mismatch")
    return expected


def _load_campaign(path: Path) -> dict[str, Any]:
    campaign = _read_object(path, "campaign manifest")
    if campaign.get("schema_version") != CAMPAIGN_SCHEMA_VERSION:
        raise ValueError("unsupported campaign manifest schema")
    _verify_self_digest(campaign, "manifest_sha256", "campaign manifest")
    books = campaign.get("books")
    if not isinstance(books, list) or not books:
        raise ValueError("campaign manifest books must be a non-empty array")
    seen_books: set[str] = set()
    for book in books:
        if not isinstance(book, Mapping):
            raise ValueError("campaign manifest book must be an object")
        book_name = book.get("book_name")
        pages = book.get("pages")
        if not isinstance(book_name, str) or not book_name or not isinstance(pages, list) or not pages:
            raise ValueError("campaign manifest book is invalid")
        if book_name in seen_books:
            raise ValueError("campaign manifest has duplicate books")
        seen_books.add(book_name)
        page_numbers: set[int] = set()
        for page in pages:
            if not isinstance(page, Mapping) or not isinstance(page.get("page_no"), int) or page["page_no"] < 1:
                raise ValueError("campaign manifest page is invalid")
            _require_sha256(page.get("image_sha256"), "campaign image_sha256")
            if page["page_no"] in page_numbers:
                raise ValueError("campaign manifest has duplicate pages")
            page_numbers.add(page["page_no"])
    return campaign


def _load_pilot(path: Path) -> dict[str, Any]:
    pilot = _read_object(path, "pilot manifest")
    if pilot.get("schema_version") != PILOT_SCHEMA_VERSION:
        raise ValueError("unsupported pilot manifest schema")
    _verify_self_digest(pilot, "pilot_sha256", "pilot manifest")
    samples = pilot.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("pilot manifest samples must be a non-empty array")
    identities: set[tuple[str, int]] = set()
    for sample in samples:
        if not isinstance(sample, Mapping):
            raise ValueError("pilot sample must be an object")
        book_name, page_no = sample.get("book_name"), sample.get("page_no")
        if not isinstance(book_name, str) or not isinstance(page_no, int) or page_no < 1:
            raise ValueError("pilot sample page key is invalid")
        if (book_name, page_no) in identities:
            raise ValueError("pilot manifest contains duplicate page keys")
        identities.add((book_name, page_no))
        _require_sha256(sample.get("image_sha256"), "pilot image_sha256")
    return pilot


def _load_b35(path: Path) -> dict[str, Any]:
    """Validate B-35 as an exclusion source without importing its implementation."""
    b35 = _read_object(path, "B-35 formal manifest")
    if b35.get("schema_version") != B35_SCHEMA_VERSION:
        raise ValueError("unsupported B-35 formal manifest schema")
    if b35.get("purpose") != "b35_final" or b35.get("state") != "sealed":
        raise ValueError("B-35 formal manifest is not a sealed formal holdout")
    _verify_self_digest(b35, "manifest_sha256", "B-35 formal manifest")
    entries = b35.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("B-35 formal manifest entries must be a non-empty array")
    seen_images: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("B-35 formal manifest entry must be an object")
        image_sha = _require_sha256(entry.get("image_sha256"), "B-35 image_sha256")
        if image_sha in seen_images:
            raise ValueError("B-35 formal manifest contains duplicate image SHA")
        seen_images.add(image_sha)
    return b35


def _excluded_identities(
    pilots: Sequence[Mapping[str, Any]], b35: Mapping[str, Any]
) -> tuple[set[tuple[str, int]], set[str], str]:
    page_keys: set[tuple[str, int]] = set()
    image_shas: set[str] = set()
    pilot_digests: list[str] = []
    for pilot in pilots:
        pilot_digests.append(str(pilot["pilot_sha256"]))
        for sample in pilot["samples"]:
            page_keys.add((str(sample["book_name"]), int(sample["page_no"])))
            image_shas.add(str(sample["image_sha256"]))
    for entry in b35["entries"]:
        image_shas.add(str(entry["image_sha256"]))
        book_name, page_no = entry.get("book_name"), entry.get("page_no")
        if isinstance(book_name, str) and isinstance(page_no, int) and page_no > 0:
            page_keys.add((book_name, page_no))
    exclusions = {
        "pilot_manifest_sha256": sorted(pilot_digests),
        "b35_manifest_sha256": str(b35["manifest_sha256"]),
        "page_keys": [{"book_name": book, "page_no": page} for book, page in sorted(page_keys)],
        "image_sha256": sorted(image_shas),
    }
    return page_keys, image_shas, canonical_sha256(exclusions)


def _rank(seed: str, book_name: str, page_no: int, image_sha256: str) -> str:
    return hashlib.sha256(f"{seed}\0{book_name}\0{page_no}\0{image_sha256}".encode()).hexdigest()


def _interior_pages(book: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    pages = sorted(book["pages"], key=lambda page: int(page["page_no"]))
    page_count = len(pages)
    lower = max(2, (page_count + 4) // 5)
    upper = min(page_count - 1, (page_count * 4) // 5)
    return [page for page in pages if lower <= int(page["page_no"]) <= upper]


def _select_samples(
    campaign: Mapping[str, Any],
    *,
    excluded_page_keys: set[tuple[str, int]],
    excluded_image_shas: set[str],
    seed: str,
    canonical_books: int,
    image_only_books: int,
) -> list[dict[str, Any]]:
    if canonical_books < 0 or image_only_books < 0 or canonical_books + image_only_books < 1:
        raise ValueError("holdout book counts must select at least one book")
    candidates: dict[str, list[dict[str, Any]]] = {"canonical": [], "image_only": []}
    for book in campaign["books"]:
        group = "canonical" if bool(book.get("has_canonical_ocr")) else "image_only"
        book_name = str(book["book_name"])
        eligible = []
        for page in _interior_pages(book):
            page_no, image_sha = int(page["page_no"]), str(page["image_sha256"])
            if (book_name, page_no) in excluded_page_keys or image_sha in excluded_image_shas:
                continue
            eligible.append(
                {
                    "book_name": book_name,
                    "page_no": page_no,
                    "image_path": str(page["image_path"]),
                    "image_sha256": image_sha,
                    "group": group,
                    "rank": _rank(seed, book_name, page_no, image_sha),
                }
            )
        if eligible:
            candidates[group].append(min(eligible, key=lambda item: (str(item["rank"]), int(item["page_no"]))))

    selected: list[dict[str, Any]] = []
    for group, count in (("canonical", canonical_books), ("image_only", image_only_books)):
        group_candidates = sorted(candidates[group], key=lambda item: (str(item["rank"]), str(item["book_name"])))
        if len(group_candidates) < count:
            raise ValueError(f"not enough eligible {group} books: {len(group_candidates)}/{count}")
        selected.extend(group_candidates[:count])
    selected.sort(key=lambda item: (str(item["group"]), str(item["rank"]), str(item["book_name"])))
    return [
        {
            "sample_id": f"fresh-{index:03d}",
            "group": item["group"],
            "book_name": item["book_name"],
            "page_no": item["page_no"],
            "image_path": item["image_path"],
            "image_sha256": item["image_sha256"],
            "selection_rank": item["rank"],
        }
        for index, item in enumerate(selected, start=1)
    ]


def _selection_output_sha256(samples: Sequence[Mapping[str, Any]]) -> str:
    return canonical_sha256(
        [
            {
                "group": str(sample["group"]),
                "book_name": str(sample["book_name"]),
                "page_no": int(sample["page_no"]),
                "image_sha256": str(sample["image_sha256"]),
                "selection_rank": str(sample["selection_rank"]),
            }
            for sample in samples
        ]
    )


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def create_formal_holdout_manifest(
    *,
    campaign_manifest_path: Path,
    pilot_manifest_paths: Sequence[Path],
    b35_manifest_path: Path,
    output_path: Path,
    holdout_id: str,
    seed: str,
    prompt_sha256: str,
    policy_sha256: str,
    canonical_books: int,
    image_only_books: int,
    sealed_at: str | None = None,
) -> dict[str, Any]:
    """Select, seal, and atomically persist a quality-blind fresh holdout."""
    if not holdout_id or not seed:
        raise ValueError("holdout_id and seed must be non-empty")
    _require_sha256(prompt_sha256, "prompt_sha256")
    _require_sha256(policy_sha256, "policy_sha256")
    sealed_at = _parse_timestamp(sealed_at or datetime.now(UTC).isoformat(), "sealed_at")
    campaign = _load_campaign(campaign_manifest_path)
    pilots = [_load_pilot(path) for path in pilot_manifest_paths]
    if len({str(pilot["pilot_sha256"]) for pilot in pilots}) != len(pilots):
        raise ValueError("pilot manifests must be unique")
    b35 = _load_b35(b35_manifest_path)
    excluded_page_keys, excluded_image_shas, exclusions_sha256 = _excluded_identities(pilots, b35)
    samples = _select_samples(
        campaign,
        excluded_page_keys=excluded_page_keys,
        excluded_image_shas=excluded_image_shas,
        seed=seed,
        canonical_books=canonical_books,
        image_only_books=image_only_books,
    )
    selection_input = {
        "campaign_manifest_sha256": str(campaign["manifest_sha256"]),
        "exclusions_sha256": exclusions_sha256,
        "seed": seed,
        "selection_policy": SELECTION_POLICY,
        "canonical_books": canonical_books,
        "image_only_books": image_only_books,
    }
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "holdout_id": holdout_id,
        "purpose": "formal",
        "state": "sealed",
        "prompt_sha256": prompt_sha256,
        "policy_sha256": policy_sha256,
        "seed": seed,
        "campaign_manifest_sha256": str(campaign["manifest_sha256"]),
        "exclusions_sha256": exclusions_sha256,
        "selection_input_sha256": canonical_sha256(selection_input),
        "selection_output_sha256": _selection_output_sha256(samples),
        "sealed_at": sealed_at,
        "samples": samples,
    }
    manifest = {**body, "manifest_sha256": canonical_sha256(body)}
    verify_formal_holdout_manifest(
        manifest,
        campaign_manifest_path=campaign_manifest_path,
        pilot_manifest_paths=pilot_manifest_paths,
        b35_manifest_path=b35_manifest_path,
    )
    _atomic_write_json(output_path, manifest)
    return manifest


def load_formal_holdout_manifest(path: Path) -> dict[str, Any]:
    manifest = _read_object(path, "Sol fresh holdout manifest")
    _verify_formal_manifest_shape(manifest)
    return manifest


def _verify_formal_manifest_shape(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported Sol fresh holdout manifest schema")
    if manifest.get("purpose") != "formal" or manifest.get("state") != "sealed":
        raise ValueError("Sol fresh holdout must be a sealed formal manifest")
    _verify_self_digest(manifest, "manifest_sha256", "Sol fresh holdout manifest")
    for key in (
        "prompt_sha256",
        "policy_sha256",
        "campaign_manifest_sha256",
        "exclusions_sha256",
        "selection_input_sha256",
        "selection_output_sha256",
    ):
        _require_sha256(manifest.get(key), key)
    if not isinstance(manifest.get("holdout_id"), str) or not manifest["holdout_id"]:
        raise ValueError("Sol fresh holdout_id must be non-empty")
    if not isinstance(manifest.get("seed"), str) or not manifest["seed"]:
        raise ValueError("Sol fresh holdout seed must be non-empty")
    _parse_timestamp(manifest.get("sealed_at"), "sealed_at")
    samples = manifest.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("Sol fresh holdout samples must be a non-empty array")
    keys: set[tuple[str, int]] = set()
    images: set[str] = set()
    books: set[str] = set()
    for sample in samples:
        if not isinstance(sample, Mapping):
            raise ValueError("Sol fresh holdout sample must be an object")
        if sample.get("group") not in {"canonical", "image_only"}:
            raise ValueError("Sol fresh holdout sample group is invalid")
        book_name, page_no = sample.get("book_name"), sample.get("page_no")
        if not isinstance(book_name, str) or not book_name or not isinstance(page_no, int) or page_no < 1:
            raise ValueError("Sol fresh holdout sample page key is invalid")
        if not isinstance(sample.get("image_path"), str) or not sample["image_path"]:
            raise ValueError("Sol fresh holdout sample image path is invalid")
        image_sha = _require_sha256(sample.get("image_sha256"), "Sol fresh holdout image_sha256")
        rank = _require_sha256(sample.get("selection_rank"), "Sol fresh holdout selection_rank")
        if (book_name, page_no) in keys or image_sha in images or book_name in books:
            raise ValueError("Sol fresh holdout samples overlap")
        keys.add((book_name, page_no))
        images.add(image_sha)
        books.add(book_name)
        if _rank(str(manifest["seed"]), book_name, page_no, image_sha) != rank:
            raise ValueError("Sol fresh holdout selection rank mismatch")
    if manifest.get("selection_output_sha256") != _selection_output_sha256(samples):
        raise ValueError("Sol fresh holdout selection output digest mismatch")


def verify_formal_holdout_manifest(
    manifest: Mapping[str, Any],
    *,
    campaign_manifest_path: Path,
    pilot_manifest_paths: Sequence[Path],
    b35_manifest_path: Path,
) -> dict[str, Any]:
    """Reproduce selection inputs and reject any overlap or digest substitution."""
    _verify_formal_manifest_shape(manifest)
    campaign = _load_campaign(campaign_manifest_path)
    pilots = [_load_pilot(path) for path in pilot_manifest_paths]
    if len({str(pilot["pilot_sha256"]) for pilot in pilots}) != len(pilots):
        raise ValueError("pilot manifests must be unique")
    b35 = _load_b35(b35_manifest_path)
    keys, images, exclusions_sha256 = _excluded_identities(pilots, b35)
    if manifest["campaign_manifest_sha256"] != campaign["manifest_sha256"]:
        raise ValueError("Sol fresh holdout campaign digest mismatch")
    if manifest["exclusions_sha256"] != exclusions_sha256:
        raise ValueError("Sol fresh holdout exclusions digest mismatch")
    group_counts = {"canonical": 0, "image_only": 0}
    campaign_pages = {
        (str(book["book_name"]), int(page["page_no"])): (book, page)
        for book in campaign["books"]
        for page in book["pages"]
    }
    for sample in manifest["samples"]:
        key = (str(sample["book_name"]), int(sample["page_no"]))
        if key in keys or str(sample["image_sha256"]) in images:
            raise ValueError("Sol fresh holdout overlaps an excluded sample")
        campaign_pair = campaign_pages.get(key)
        if campaign_pair is None:
            raise ValueError("Sol fresh holdout sample is absent from campaign")
        book, page = campaign_pair
        if sample["image_sha256"] != page["image_sha256"] or sample["image_path"] != page["image_path"]:
            raise ValueError("Sol fresh holdout campaign image mismatch")
        expected_group = "canonical" if bool(book.get("has_canonical_ocr")) else "image_only"
        if sample["group"] != expected_group or page not in _interior_pages(book):
            raise ValueError("Sol fresh holdout sample violates selection policy")
        group_counts[str(sample["group"])] += 1
    selection_input = {
        "campaign_manifest_sha256": str(campaign["manifest_sha256"]),
        "exclusions_sha256": exclusions_sha256,
        "seed": str(manifest["seed"]),
        "selection_policy": SELECTION_POLICY,
        "canonical_books": group_counts["canonical"],
        "image_only_books": group_counts["image_only"],
    }
    if manifest["selection_input_sha256"] != canonical_sha256(selection_input):
        raise ValueError("Sol fresh holdout selection input digest mismatch")
    expected = _select_samples(
        campaign,
        excluded_page_keys=keys,
        excluded_image_shas=images,
        seed=str(manifest["seed"]),
        canonical_books=group_counts["canonical"],
        image_only_books=group_counts["image_only"],
    )
    if manifest["samples"] != expected:
        raise ValueError("Sol fresh holdout selection output was modified")
    return {
        "manifest_sha256": str(manifest["manifest_sha256"]),
        "sample_count": len(expected),
        "canonical_books": group_counts["canonical"],
        "image_only_books": group_counts["image_only"],
    }


def _timestamp(value: str | None) -> str:
    return _parse_timestamp(value or datetime.now(UTC).isoformat(), "occurred_at")


def _read_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": LEDGER_SCHEMA_VERSION, "events": []}
    ledger = _read_object(path, "Sol fresh holdout ledger")
    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION or not isinstance(ledger.get("events"), list):
        raise ValueError("unsupported Sol fresh holdout ledger schema")
    return ledger


@contextmanager
def _ledger_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("Sol fresh holdout ledger is locked by another process") from exc
    os.close(descriptor)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _events_for(ledger: Mapping[str, Any], manifest_sha256: str) -> list[Mapping[str, Any]]:
    return [
        event
        for event in ledger["events"]
        if isinstance(event, Mapping) and event.get("manifest_sha256") == manifest_sha256
    ]


def verify_formal_holdout_is_opened(ledger_path: Path, manifest: Mapping[str, Any]) -> None:
    """Require the manifest's latest ledger state to be opened."""
    _verify_formal_manifest_shape(manifest)
    events = _events_for(_read_ledger(ledger_path), str(manifest["manifest_sha256"]))
    if not events or events[-1].get("state") != "opened":
        raise ValueError("Sol fresh holdout must be opened and not retired")


def export_formal_holdout_images(
    *,
    manifest: Mapping[str, Any],
    ledger_path: Path,
    images_root: Path,
    output_tar: Path,
) -> None:
    """Export an opened holdout after revalidating every source image."""
    verify_formal_holdout_is_opened(ledger_path, manifest)
    image_root = images_root.resolve(strict=True)
    output_tar.parent.mkdir(parents=True, exist_ok=True)
    temporary_tar = output_tar.with_name(f".{output_tar.name}.tmp")
    try:
        with tarfile.open(temporary_tar, "w") as archive:
            for sample in manifest["samples"]:
                image_path = (image_root / str(sample["image_path"])).resolve(strict=True)
                if not image_path.is_relative_to(image_root):
                    raise ValueError("Sol fresh holdout image escaped images root")
                if not image_path.is_file():
                    raise ValueError(f"Sol fresh holdout source image is not a file: {sample['sample_id']}")
                with image_path.open("rb") as source:
                    image_sha256 = hashlib.file_digest(source, "sha256").hexdigest()
                if image_sha256 != sample["image_sha256"]:
                    raise ValueError(f"Sol fresh holdout source image changed: {sample['sample_id']}")
                archive.add(image_path, arcname=f"images/{sample['image_path']}", recursive=False)
        os.replace(temporary_tar, output_tar)
    except BaseException:
        temporary_tar.unlink(missing_ok=True)
        raise


def record_sealed_manifest(
    ledger_path: Path, manifest: Mapping[str, Any], *, operator: str, occurred_at: str | None = None
) -> None:
    _verify_formal_manifest_shape(manifest)
    if not operator.strip():
        raise ValueError("Sol fresh holdout sealing requires operator")
    manifest_sha = str(manifest["manifest_sha256"])
    with _ledger_lock(ledger_path):
        ledger = _read_ledger(ledger_path)
        if _events_for(ledger, manifest_sha):
            raise ValueError("Sol fresh holdout manifest is already recorded")
        ledger["events"].append(
            {
                "manifest_sha256": manifest_sha,
                "state": "sealed",
                "operator": operator,
                "occurred_at": _timestamp(occurred_at),
            }
        )
        _atomic_write_json(ledger_path, ledger)


def open_formal_holdout(
    ledger_path: Path, manifest: Mapping[str, Any], *, operator: str, reason: str, occurred_at: str | None = None
) -> None:
    _verify_formal_manifest_shape(manifest)
    if not operator.strip() or not reason.strip():
        raise ValueError("Sol fresh holdout opening requires operator and reason")
    manifest_sha = str(manifest["manifest_sha256"])
    with _ledger_lock(ledger_path):
        ledger = _read_ledger(ledger_path)
        events = _events_for(ledger, manifest_sha)
        if not events or events[-1].get("state") != "sealed":
            if any(event.get("state") == "opened" for event in events):
                raise ValueError("Sol fresh holdout was already opened")
            raise ValueError("Sol fresh holdout must be sealed before opening")
        ledger["events"].append(
            {
                "manifest_sha256": manifest_sha,
                "state": "opened",
                "operator": operator,
                "reason": reason,
                "occurred_at": _timestamp(occurred_at),
            }
        )
        _atomic_write_json(ledger_path, ledger)


def retire_formal_holdout_to_tuning(
    ledger_path: Path, manifest: Mapping[str, Any], *, operator: str, reason: str, occurred_at: str | None = None
) -> None:
    _verify_formal_manifest_shape(manifest)
    if not operator.strip() or not reason.strip():
        raise ValueError("Sol fresh holdout retirement requires operator and reason")
    manifest_sha = str(manifest["manifest_sha256"])
    with _ledger_lock(ledger_path):
        ledger = _read_ledger(ledger_path)
        events = _events_for(ledger, manifest_sha)
        if any(event.get("state") == "retired_to_tuning" for event in events):
            raise ValueError("Sol fresh holdout is already retired to tuning")
        if not events or events[-1].get("state") != "opened":
            raise ValueError("Sol fresh holdout must be opened before retirement")
        ledger["events"].append(
            {
                "manifest_sha256": manifest_sha,
                "state": "retired_to_tuning",
                "operator": operator,
                "reason": reason,
                "occurred_at": _timestamp(occurred_at),
            }
        )
        _atomic_write_json(ledger_path, ledger)
