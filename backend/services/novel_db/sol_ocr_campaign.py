"""Immutable manifest generation for the versioned Sol image-OCR campaign."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

SCHEMA_VERSION = "sol-ocr-campaign-v1"
PILOT_SCHEMA_VERSION = "sol-ocr-pilot-v1"
PAGE_ARTIFACT_SCHEMA_VERSION = "sol-ocr-page-v1"
PAGE_CANDIDATE_V2_SCHEMA_VERSION = "sol-ocr-page-v2"
CHECKER_ARTIFACT_V2_SCHEMA_VERSION = "sol-ocr-checker-v2"
RESOLVED_ARTIFACT_V2_SCHEMA_VERSION = "sol-ocr-resolved-v2"
SOL_MODEL = "gpt-5.6-sol"
SOL_PROMPT_VERSION = "sol-image-ocr-v1"

_V2_PURPOSES = {"tuning", "formal"}
_V2_CANDIDATE_IDS = {"a", "b"}
_V2_COVERAGE_STATES = {"complete", "incomplete", "uncertain"}
_V2_READING_ORDER_STATES = {"pass", "fail", "uncertain"}
_V2_VERDICTS = {"pass", "needs_review", "fail"}


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as output:
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


def _canonical_counts(db_path: Path | None, book_name: str, page_count: int) -> tuple[int, bool]:
    if db_path is None:
        return 0, False
    uri = f"file:{db_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row = conn.execute(
            "SELECT b.id, COUNT(p.id) FROM books b "
            "LEFT JOIN pages p ON p.book_id=b.id AND p.page_no BETWEEN 1 AND ? "
            "WHERE b.name=? GROUP BY b.id",
            (page_count, book_name),
        ).fetchone()
    canonical_page_count = 0 if row is None else int(row[1])
    return canonical_page_count, canonical_page_count == page_count


def _collect_book(images_root: Path, book_dir: Path, db_path: Path | None) -> dict[str, Any]:
    if book_dir.is_symlink():
        raise ValueError(f"symlink book directory is not allowed: {book_dir.name}")
    numbered: list[tuple[int, Path]] = []
    for image_path in book_dir.glob("*.png"):
        if image_path.is_symlink():
            raise ValueError(f"symlink image is not allowed: {book_dir.name}/{image_path.name}")
        if image_path.is_file() and image_path.stem.isdigit():
            numbered.append((int(image_path.stem), image_path))
    numbered.sort(key=lambda item: item[0])
    if not numbered:
        raise ValueError(f"no numbered PNG images found in: {book_dir.name}")
    actual = [page_no for page_no, _ in numbered]
    expected = list(range(1, len(numbered) + 1))
    if actual != expected:
        raise ValueError(f"PNG page numbers must be contiguous from 1: {book_dir.name}: {actual}")

    pages: list[dict[str, Any]] = []
    for page_no, image_path in numbered:
        with Image.open(image_path) as image:
            image.verify()
        pages.append(
            {
                "page_no": page_no,
                "image_path": image_path.relative_to(images_root).as_posix(),
                "image_sha256": _sha256_file(image_path),
                "size_bytes": image_path.stat().st_size,
            }
        )
    canonical_page_count, has_canonical_ocr = _canonical_counts(db_path, book_dir.name, len(pages))
    return {
        "book_name": book_dir.name,
        "page_count": len(pages),
        "canonical_page_count": canonical_page_count,
        "has_canonical_ocr": has_canonical_ocr,
        "pages": pages,
    }


def _partition_books(books: list[dict[str, Any]], worker_count: int) -> list[dict[str, Any]]:
    if worker_count < 1:
        raise ValueError("worker_count must be at least 1")
    assignments: list[list[dict[str, Any]]] = [[] for _ in range(worker_count)]
    totals = [0] * worker_count
    for book in sorted(books, key=lambda item: (-int(item["page_count"]), str(item["book_name"]))):
        worker_index = min(range(worker_count), key=lambda index: (totals[index], index))
        assignments[worker_index].append(book)
        totals[worker_index] += int(book["page_count"])

    partitions: list[dict[str, Any]] = []
    for index, assigned in enumerate(assignments, start=1):
        book_refs = [
            {"book_name": str(book["book_name"]), "page_count": int(book["page_count"])}
            for book in sorted(assigned, key=lambda item: str(item["book_name"]))
        ]
        partition_body = {
            "worker_id": f"worker-{index}",
            "book_count": len(book_refs),
            "page_count": sum(int(book["page_count"]) for book in book_refs),
            "books": book_refs,
        }
        partitions.append(
            {
                **partition_body,
                "partition_sha256": hashlib.sha256(_canonical_json(partition_body)).hexdigest(),
            }
        )
    return partitions


def create_manifest(
    *,
    images_root: Path,
    campaign_id: str,
    output_dir: Path,
    worker_count: int = 3,
    db_path: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Hash, validate, partition, and atomically persist a campaign manifest."""
    images_root = images_root.resolve(strict=True)
    if not images_root.is_dir():
        raise NotADirectoryError(images_root)
    if not campaign_id or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in campaign_id
    ):
        raise ValueError("campaign_id must contain only ASCII letters, digits, '-' or '_'")
    if db_path is not None:
        db_path = db_path.resolve(strict=True)

    book_dirs = sorted((path for path in images_root.iterdir() if path.is_dir()), key=lambda path: path.name)
    books = [_collect_book(images_root, book_dir, db_path) for book_dir in book_dirs]
    partitions = _partition_books(books, worker_count)
    summary = {
        "book_count": len(books),
        "page_count": sum(int(book["page_count"]) for book in books),
        "canonical_book_count": sum(bool(book["has_canonical_ocr"]) for book in books),
        "canonical_page_count": sum(int(book["canonical_page_count"]) for book in books),
        "image_only_book_count": sum(not bool(book["has_canonical_ocr"]) for book in books),
    }
    body = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "created_at": created_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_root_label": "kindle_novel/images",
        "summary": summary,
        "books": books,
        "partitions": partitions,
    }
    manifest = {**body, "manifest_sha256": hashlib.sha256(_canonical_json(body)).hexdigest()}
    manifest_path = output_dir / campaign_id / "manifest.json"
    _atomic_write_json(manifest_path, manifest)
    for partition in partitions:
        _atomic_write_json(
            manifest_path.parent / f"{partition['worker_id']}.json",
            {
                "schema_version": SCHEMA_VERSION,
                "campaign_id": campaign_id,
                "manifest_sha256": manifest["manifest_sha256"],
                **partition,
            },
        )
    return manifest


def verify_manifest(manifest_path: Path, images_root: Path, *, verify_images: bool = True) -> dict[str, Any]:
    """Verify the manifest digest and, optionally, every current source image."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_digest = str(manifest.pop("manifest_sha256", ""))
    actual_digest = hashlib.sha256(_canonical_json(manifest)).hexdigest()
    manifest["manifest_sha256"] = expected_digest
    if actual_digest != expected_digest:
        raise ValueError("campaign manifest digest mismatch")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported campaign manifest schema")

    if verify_images:
        images_root = images_root.resolve(strict=True)
        for book in manifest["books"]:
            for page in book["pages"]:
                image_path = (images_root / str(page["image_path"])).resolve(strict=True)
                if not image_path.is_relative_to(images_root):
                    raise ValueError("manifest image escaped images root")
                if image_path.stat().st_size != int(page["size_bytes"]):
                    raise ValueError(f"source image size changed: {page['image_path']}")
                if _sha256_file(image_path) != str(page["image_sha256"]):
                    raise ValueError(f"source image changed: {page['image_path']}")
    return manifest


def _evenly_spaced_books(books: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    eligible = sorted((book for book in books if int(book["page_count"]) >= 3), key=lambda book: str(book["book_name"]))
    if len(eligible) < count:
        raise ValueError(f"not enough books for pilot selection: {len(eligible)}/{count}")
    if count == 1:
        return [eligible[len(eligible) // 2]]
    indices = [round(index * (len(eligible) - 1) / (count - 1)) for index in range(count)]
    return [eligible[index] for index in indices]


def create_pilot_manifest(
    *,
    campaign_manifest: dict[str, Any],
    output_path: Path,
    image_only_books: int = 8,
    canonical_books: int = 19,
) -> dict[str, Any]:
    """Select first/middle/last pages across 27 books for the fixed 24+57 pilot."""
    groups = (
        (
            "image_only",
            _evenly_spaced_books(
                [book for book in campaign_manifest["books"] if not bool(book["has_canonical_ocr"])],
                image_only_books,
            ),
        ),
        (
            "canonical",
            _evenly_spaced_books(
                [book for book in campaign_manifest["books"] if bool(book["has_canonical_ocr"])],
                canonical_books,
            ),
        ),
    )
    samples: list[dict[str, Any]] = []
    sample_index = 0
    for group_name, books in groups:
        for book in books:
            page_count = int(book["page_count"])
            page_numbers = (1, (page_count + 1) // 2, page_count)
            pages_by_no = {int(page["page_no"]): page for page in book["pages"]}
            for page_no in page_numbers:
                page = pages_by_no[page_no]
                samples.append(
                    {
                        "sample_id": f"pilot-{sample_index + 1:03d}",
                        "group": group_name,
                        "worker_id": f"worker-{(sample_index % 3) + 1}",
                        "book_name": str(book["book_name"]),
                        "page_no": page_no,
                        "image_path": str(page["image_path"]),
                        "image_sha256": str(page["image_sha256"]),
                    }
                )
                sample_index += 1
    body = {
        "schema_version": PILOT_SCHEMA_VERSION,
        "campaign_id": campaign_manifest["campaign_id"],
        "manifest_sha256": campaign_manifest["manifest_sha256"],
        "summary": {
            "sample_count": len(samples),
            "image_only_samples": sum(sample["group"] == "image_only" for sample in samples),
            "canonical_samples": sum(sample["group"] == "canonical" for sample in samples),
        },
        "samples": samples,
    }
    pilot = {**body, "pilot_sha256": hashlib.sha256(_canonical_json(body)).hexdigest()}
    _atomic_write_json(output_path, pilot)
    return pilot


def load_pilot_manifest(path: Path) -> dict[str, Any]:
    pilot = json.loads(path.read_text(encoding="utf-8"))
    expected_digest = str(pilot.pop("pilot_sha256", ""))
    actual_digest = hashlib.sha256(_canonical_json(pilot)).hexdigest()
    pilot["pilot_sha256"] = expected_digest
    if actual_digest != expected_digest:
        raise ValueError("pilot manifest digest mismatch")
    if pilot.get("schema_version") != PILOT_SCHEMA_VERSION:
        raise ValueError("unsupported pilot manifest schema")
    sample_ids = [str(sample["sample_id"]) for sample in pilot["samples"]]
    page_keys = [(str(sample["book_name"]), int(sample["page_no"])) for sample in pilot["samples"]]
    if len(sample_ids) != len(set(sample_ids)) or len(page_keys) != len(set(page_keys)):
        raise ValueError("pilot manifest contains duplicate samples")
    return pilot


def export_pilot_images(*, pilot_manifest: dict[str, Any], images_root: Path, output_tar: Path) -> None:
    """Export only pilot images, keeping their manifest-relative names."""
    images_root = images_root.resolve(strict=True)
    output_tar.parent.mkdir(parents=True, exist_ok=True)
    temporary_tar = output_tar.with_name(f".{output_tar.name}.tmp")
    try:
        with tarfile.open(temporary_tar, "w") as archive:
            for sample in pilot_manifest["samples"]:
                image_path = (images_root / str(sample["image_path"])).resolve(strict=True)
                if not image_path.is_relative_to(images_root):
                    raise ValueError("pilot image escaped images root")
                if _sha256_file(image_path) != str(sample["image_sha256"]):
                    raise ValueError(f"pilot source image changed: {sample['sample_id']}")
                archive.add(image_path, arcname=f"images/{sample['image_path']}", recursive=False)
        os.replace(temporary_tar, output_tar)
    except BaseException:
        try:
            temporary_tar.unlink()
        except FileNotFoundError:
            pass
        raise


def load_page_artifact(path: Path) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "campaign_id",
        "manifest_sha256",
        "pilot_sha256",
        "sample_id",
        "worker_id",
        "model",
        "prompt_version",
        "book_name",
        "page_no",
        "image_sha256",
        "text",
        "transcription_notes",
        "processed_at",
    }
    if set(artifact) != required:
        raise ValueError("unsupported Sol OCR page artifact fields")
    if artifact["schema_version"] != PAGE_ARTIFACT_SCHEMA_VERSION:
        raise ValueError("unsupported Sol OCR page artifact schema")
    if artifact["model"] != SOL_MODEL or artifact["prompt_version"] != SOL_PROMPT_VERSION:
        raise ValueError("unexpected Sol OCR model or prompt version")
    for field in ("campaign_id", "sample_id", "worker_id", "book_name", "processed_at"):
        if not isinstance(artifact[field], str) or not artifact[field]:
            raise ValueError(f"Sol OCR {field} must be a non-empty string")
    for field in ("manifest_sha256", "pilot_sha256", "image_sha256"):
        value = artifact[field]
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"Sol OCR {field} must be a lowercase SHA-256")
    try:
        processed_at = datetime.fromisoformat(artifact["processed_at"])
    except ValueError as exc:
        raise ValueError("Sol OCR processed_at must be ISO-8601") from exc
    if processed_at.tzinfo is None:
        raise ValueError("Sol OCR processed_at must include a timezone")
    if not isinstance(artifact["text"], str):
        raise ValueError("Sol OCR text must be a string")
    notes = artifact["transcription_notes"]
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        raise ValueError("Sol OCR transcription_notes must be a string list")
    if not isinstance(artifact["page_no"], int) or artifact["page_no"] < 1:
        raise ValueError("Sol OCR page_no must be a positive integer")
    return artifact


def validate_page_artifact(
    artifact: dict[str, Any],
    *,
    pilot_manifest: dict[str, Any],
    images_root: Path,
) -> dict[str, Any]:
    if artifact["campaign_id"] != pilot_manifest["campaign_id"]:
        raise ValueError("Sol OCR artifact campaign mismatch")
    if artifact["manifest_sha256"] != pilot_manifest["manifest_sha256"]:
        raise ValueError("Sol OCR artifact manifest mismatch")
    if artifact["pilot_sha256"] != pilot_manifest["pilot_sha256"]:
        raise ValueError("Sol OCR artifact pilot mismatch")
    samples = {sample["sample_id"]: sample for sample in pilot_manifest["samples"]}
    sample = samples.get(artifact["sample_id"])
    if sample is None:
        raise ValueError("Sol OCR artifact sample is not in pilot manifest")
    for field in ("worker_id", "book_name", "page_no", "image_sha256"):
        if artifact[field] != sample[field]:
            raise ValueError(f"Sol OCR artifact {field} mismatch")
    image_path = (images_root.resolve(strict=True) / str(sample["image_path"])).resolve(strict=True)
    if not image_path.is_relative_to(images_root.resolve()):
        raise ValueError("pilot image escaped images root")
    if _sha256_file(image_path) != artifact["image_sha256"]:
        raise ValueError("Sol OCR artifact source image changed")
    return sample


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _validate_lower_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _validate_non_empty_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _validate_timestamp(value: object, *, label: str) -> str:
    timestamp = _validate_non_empty_string(value, label=label)
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return timestamp


def _validate_string_list(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string list")
    return value


def _validate_artifact_digest(artifact: dict[str, Any], *, digest_field: str, label: str) -> None:
    expected = _validate_lower_sha256(artifact.get(digest_field), label=f"{label} {digest_field}")
    body = {field: value for field, value in artifact.items() if field != digest_field}
    actual = hashlib.sha256(_canonical_json(body)).hexdigest()
    if actual != expected:
        raise ValueError(f"{label} digest mismatch")


def _validate_v2_coverage(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("Sol OCR v2 coverage must be a list")
    seen_ids: set[str] = set()
    orders: list[int] = []
    for entry in value:
        required = {
            "column_id",
            "order",
            "strip_id",
            "start_anchor",
            "end_anchor",
            "text",
            "block_type",
            "ruby",
            "uncertainties",
        }
        if not isinstance(entry, dict) or set(entry) != required:
            raise ValueError("Sol OCR v2 coverage entry fields are unsupported")
        column_id = _validate_non_empty_string(entry["column_id"], label="Sol OCR v2 column_id")
        if column_id in seen_ids:
            raise ValueError("Sol OCR v2 coverage column_id must be unique")
        seen_ids.add(column_id)
        order = entry["order"]
        if type(order) is not int or order < 1:
            raise ValueError("Sol OCR v2 coverage order must be a positive integer")
        orders.append(order)
        _validate_non_empty_string(entry["strip_id"], label="Sol OCR v2 coverage strip_id")
        column_text = _validate_non_empty_string(entry["text"], label="Sol OCR v2 coverage text")
        _validate_non_empty_string(entry["block_type"], label="Sol OCR v2 coverage block_type")
        start_anchor = _validate_non_empty_string(entry["start_anchor"], label="Sol OCR v2 coverage start_anchor")
        end_anchor = _validate_non_empty_string(entry["end_anchor"], label="Sol OCR v2 coverage end_anchor")
        if start_anchor not in column_text or end_anchor not in column_text:
            raise ValueError("Sol OCR v2 coverage anchor is absent from column text")
        _validate_string_list(entry["ruby"], label="Sol OCR v2 coverage ruby")
        _validate_string_list(entry["uncertainties"], label="Sol OCR v2 coverage uncertainties")
    if orders != list(range(1, len(orders) + 1)):
        raise ValueError("Sol OCR v2 coverage order must be consecutive from 1")
    return value


def _validate_v2_candidate_fields(artifact: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "campaign_id",
        "manifest_sha256",
        "pilot_sha256",
        "purpose",
        "model",
        "prompt_sha256",
        "policy_sha256",
        "sample_id",
        "book_name",
        "page_no",
        "image_sha256",
        "session_id",
        "worker_id",
        "candidate_id",
        "coverage",
        "text",
        "transcription_notes",
        "processed_at",
        "candidate_sha256",
    }
    if set(artifact) != required:
        raise ValueError("unsupported Sol OCR v2 candidate artifact fields")
    if artifact["schema_version"] != PAGE_CANDIDATE_V2_SCHEMA_VERSION:
        raise ValueError("unsupported Sol OCR v2 candidate artifact schema")
    if artifact["purpose"] not in _V2_PURPOSES:
        raise ValueError("unsupported Sol OCR v2 candidate purpose")
    if artifact["model"] != SOL_MODEL:
        raise ValueError("unexpected Sol OCR v2 candidate model")
    _validate_artifact_digest(artifact, digest_field="candidate_sha256", label="Sol OCR v2 candidate")
    for field in ("campaign_id", "sample_id", "book_name", "session_id", "worker_id"):
        _validate_non_empty_string(artifact[field], label=f"Sol OCR v2 {field}")
    for field in ("manifest_sha256", "pilot_sha256", "prompt_sha256", "policy_sha256", "image_sha256"):
        _validate_lower_sha256(artifact[field], label=f"Sol OCR v2 {field}")
    if artifact["candidate_id"] not in _V2_CANDIDATE_IDS:
        raise ValueError("unsupported Sol OCR v2 candidate_id")
    if type(artifact["page_no"]) is not int or artifact["page_no"] < 1:
        raise ValueError("Sol OCR v2 page_no must be a positive integer")
    if not isinstance(artifact["text"], str):
        raise ValueError("Sol OCR v2 text must be a string")
    coverage = _validate_v2_coverage(artifact["coverage"])
    if coverage and not artifact["text"]:
        raise ValueError("Sol OCR v2 coverage requires non-empty text")
    search_start = 0
    for entry in coverage:
        column_position = artifact["text"].find(entry["text"], search_start)
        if column_position < 0:
            raise ValueError("Sol OCR v2 coverage columns do not reconstruct text in reading order")
        search_start = column_position + len(entry["text"])
    _validate_string_list(artifact["transcription_notes"], label="Sol OCR v2 transcription_notes")
    _validate_timestamp(artifact["processed_at"], label="Sol OCR v2 processed_at")


def load_page_candidate_v2_artifact(path: Path) -> dict[str, Any]:
    """Load a self-hashed, image-only Sol v2 candidate artifact."""
    artifact = _load_json_object(path, label="Sol OCR v2 candidate artifact")
    _validate_v2_candidate_fields(artifact)
    return artifact


def build_page_candidate_v2_artifact(
    raw_candidate: dict[str, Any],
    *,
    pilot_manifest: dict[str, Any],
    purpose: str,
) -> dict[str, Any]:
    """Normalize a worker's column-rich raw result into a self-hashed v2 candidate."""
    required = {
        "sample_id",
        "book_name",
        "page_no",
        "image_sha256",
        "candidate_id",
        "producer_session_id",
        "worker_id",
        "model",
        "prompt_sha256",
        "policy_sha256",
        "processed_at",
        "visual_column_count",
        "columns",
        "strip_evidence",
        "text",
        "transcription_notes",
    }
    allowed = required | {"schema_version"}
    if set(raw_candidate) not in (required, allowed):
        raise ValueError("unsupported Sol OCR v2 raw candidate fields")
    if "schema_version" in raw_candidate and raw_candidate["schema_version"] != "sol-ocr-rescue-candidate-raw-v2":
        raise ValueError("unsupported Sol OCR v2 raw candidate schema")
    columns = raw_candidate["columns"]
    if not isinstance(columns, list) or type(raw_candidate["visual_column_count"]) is not int:
        raise ValueError("Sol OCR v2 raw candidate columns are invalid")
    if raw_candidate["visual_column_count"] != len(columns):
        raise ValueError("Sol OCR v2 raw candidate visual column count mismatch")
    strip_evidence = raw_candidate["strip_evidence"]
    if not isinstance(strip_evidence, list) or not strip_evidence:
        raise ValueError("Sol OCR v2 raw candidate strip evidence is invalid")
    strip_columns: dict[str, set[str]] = {}
    for strip in strip_evidence:
        if not isinstance(strip, dict) or set(strip) != {"strip_id", "column_ids"}:
            raise ValueError("Sol OCR v2 raw candidate strip evidence fields are unsupported")
        strip_id = _validate_non_empty_string(strip["strip_id"], label="Sol OCR v2 raw strip_id")
        if strip_id in strip_columns:
            raise ValueError("Sol OCR v2 raw strip_id must be unique")
        column_ids = strip["column_ids"]
        if not isinstance(column_ids, list) or any(not isinstance(item, str) for item in column_ids):
            raise ValueError("Sol OCR v2 raw strip column_ids must be a string list")
        strip_columns[strip_id] = set(column_ids)

    coverage: list[dict[str, Any]] = []
    for column in columns:
        if not isinstance(column, dict):
            raise ValueError("Sol OCR v2 raw candidate column must be an object")
        expected_column_fields = {
            "column_id",
            "reading_order",
            "strip_id",
            "start_anchor",
            "end_anchor",
            "text",
            "block_type",
            "ruby",
            "uncertainties",
        }
        if set(column) != expected_column_fields:
            raise ValueError("Sol OCR v2 raw candidate column fields are unsupported")
        strip_id = column["strip_id"]
        if strip_id not in strip_columns or column["column_id"] not in strip_columns[strip_id]:
            raise ValueError("Sol OCR v2 raw candidate strip evidence omits a referenced column")
        coverage.append(
            {
                "column_id": column["column_id"],
                "order": column["reading_order"],
                "strip_id": strip_id,
                "start_anchor": column["start_anchor"],
                "end_anchor": column["end_anchor"],
                "text": column["text"],
                "block_type": column["block_type"],
                "ruby": column["ruby"],
                "uncertainties": column["uncertainties"],
            }
        )

    raw_notes = raw_candidate["transcription_notes"]
    if isinstance(raw_notes, str):
        transcription_notes = [raw_notes] if raw_notes else []
    elif isinstance(raw_notes, list) and all(isinstance(note, str) for note in raw_notes):
        transcription_notes = raw_notes
    else:
        raise ValueError("Sol OCR v2 raw candidate transcription_notes must be a string or string list")

    body = {
        "schema_version": PAGE_CANDIDATE_V2_SCHEMA_VERSION,
        "campaign_id": pilot_manifest["campaign_id"],
        "manifest_sha256": pilot_manifest["manifest_sha256"],
        "pilot_sha256": pilot_manifest["pilot_sha256"],
        "purpose": purpose,
        "model": raw_candidate["model"],
        "prompt_sha256": raw_candidate["prompt_sha256"],
        "policy_sha256": raw_candidate["policy_sha256"],
        "sample_id": raw_candidate["sample_id"],
        "book_name": raw_candidate["book_name"],
        "page_no": raw_candidate["page_no"],
        "image_sha256": raw_candidate["image_sha256"],
        "session_id": raw_candidate["producer_session_id"],
        "worker_id": raw_candidate["worker_id"],
        "candidate_id": raw_candidate["candidate_id"],
        "coverage": coverage,
        "text": raw_candidate["text"],
        "transcription_notes": transcription_notes,
        "processed_at": raw_candidate["processed_at"],
    }
    artifact = {**body, "candidate_sha256": hashlib.sha256(_canonical_json(body)).hexdigest()}
    _validate_v2_candidate_fields(artifact)
    return artifact


def validate_page_candidate_v2_artifact(
    artifact: dict[str, Any],
    *,
    pilot_manifest: dict[str, Any],
    images_root: Path,
) -> dict[str, Any]:
    """Bind a v2 candidate to exactly one fixed pilot sample and image."""
    _validate_v2_candidate_fields(artifact)
    if artifact["campaign_id"] != pilot_manifest["campaign_id"]:
        raise ValueError("Sol OCR v2 candidate campaign mismatch")
    if artifact["manifest_sha256"] != pilot_manifest["manifest_sha256"]:
        raise ValueError("Sol OCR v2 candidate manifest mismatch")
    if artifact["pilot_sha256"] != pilot_manifest["pilot_sha256"]:
        raise ValueError("Sol OCR v2 candidate pilot mismatch")
    samples = {sample["sample_id"]: sample for sample in pilot_manifest["samples"]}
    sample = samples.get(artifact["sample_id"])
    if sample is None:
        raise ValueError("Sol OCR v2 candidate sample is not in pilot manifest")
    for field in ("book_name", "page_no", "image_sha256"):
        if artifact[field] != sample[field]:
            raise ValueError(f"Sol OCR v2 candidate {field} mismatch")
    image_root = images_root.resolve(strict=True)
    image_path = (image_root / str(sample["image_path"])).resolve(strict=True)
    if not image_path.is_relative_to(image_root):
        raise ValueError("Sol OCR v2 pilot image escaped images root")
    if _sha256_file(image_path) != artifact["image_sha256"]:
        raise ValueError("Sol OCR v2 candidate source image changed")
    return sample


def validate_page_candidate_pair(candidate_a: dict[str, Any], candidate_b: dict[str, Any]) -> None:
    """Require independent A/B producers for the same v2 pilot image."""
    _validate_v2_candidate_fields(candidate_a)
    _validate_v2_candidate_fields(candidate_b)
    if candidate_a["candidate_id"] != "a" or candidate_b["candidate_id"] != "b":
        raise ValueError("Sol OCR v2 candidate pair must be A then B")
    fields = (
        "campaign_id",
        "manifest_sha256",
        "pilot_sha256",
        "purpose",
        "model",
        "prompt_sha256",
        "policy_sha256",
        "sample_id",
        "book_name",
        "page_no",
        "image_sha256",
    )
    for field in fields:
        if candidate_a[field] != candidate_b[field]:
            raise ValueError(f"Sol OCR v2 candidate pair {field} mismatch")
    if candidate_a["session_id"] == candidate_b["session_id"]:
        raise ValueError("Sol OCR v2 candidates must use different sessions")
    if candidate_a["worker_id"] == candidate_b["worker_id"]:
        raise ValueError("Sol OCR v2 candidates must use different workers")


def _validate_v2_checker_fields(artifact: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "campaign_id",
        "manifest_sha256",
        "pilot_sha256",
        "purpose",
        "model",
        "prompt_sha256",
        "policy_sha256",
        "sample_id",
        "book_name",
        "page_no",
        "image_sha256",
        "session_id",
        "worker_id",
        "candidate_a_sha256",
        "candidate_b_sha256",
        "candidate_coverage",
        "reading_order",
        "major_errors",
        "selection",
        "verdict",
        "reason",
        "checked_at",
        "checker_sha256",
    }
    if set(artifact) != required:
        raise ValueError("unsupported Sol OCR v2 checker artifact fields")
    if artifact["schema_version"] != CHECKER_ARTIFACT_V2_SCHEMA_VERSION:
        raise ValueError("unsupported Sol OCR v2 checker artifact schema")
    if artifact["purpose"] not in _V2_PURPOSES:
        raise ValueError("unsupported Sol OCR v2 checker purpose")
    if artifact["model"] != SOL_MODEL:
        raise ValueError("unexpected Sol OCR v2 checker model")
    for field in ("campaign_id", "sample_id", "book_name", "session_id", "worker_id", "reason"):
        _validate_non_empty_string(artifact[field], label=f"Sol OCR v2 checker {field}")
    for field in (
        "manifest_sha256",
        "pilot_sha256",
        "prompt_sha256",
        "policy_sha256",
        "image_sha256",
        "candidate_a_sha256",
        "candidate_b_sha256",
    ):
        _validate_lower_sha256(artifact[field], label=f"Sol OCR v2 checker {field}")
    if type(artifact["page_no"]) is not int or artifact["page_no"] < 1:
        raise ValueError("Sol OCR v2 checker page_no must be a positive integer")
    coverage = artifact["candidate_coverage"]
    if not isinstance(coverage, dict) or set(coverage) != _V2_CANDIDATE_IDS:
        raise ValueError("Sol OCR v2 checker candidate_coverage must contain A and B")
    if any(state not in _V2_COVERAGE_STATES for state in coverage.values()):
        raise ValueError("unsupported Sol OCR v2 checker candidate coverage")
    if artifact["reading_order"] not in _V2_READING_ORDER_STATES:
        raise ValueError("unsupported Sol OCR v2 checker reading_order")
    _validate_string_list(artifact["major_errors"], label="Sol OCR v2 checker major_errors")
    if artifact["selection"] is not None and artifact["selection"] not in _V2_CANDIDATE_IDS:
        raise ValueError("unsupported Sol OCR v2 checker selection")
    if artifact["verdict"] not in _V2_VERDICTS:
        raise ValueError("unsupported Sol OCR v2 checker verdict")
    if artifact["verdict"] == "pass" and artifact["selection"] is None:
        raise ValueError("Sol OCR v2 checker pass requires a selection")
    if artifact["verdict"] != "pass" and artifact["selection"] is not None:
        raise ValueError("Sol OCR v2 checker non-pass cannot select a candidate")
    _validate_timestamp(artifact["checked_at"], label="Sol OCR v2 checker checked_at")
    _validate_artifact_digest(artifact, digest_field="checker_sha256", label="Sol OCR v2 checker")


def load_checker_v2_artifact(path: Path) -> dict[str, Any]:
    """Load a self-hashed third-session v2 checker artifact."""
    artifact = _load_json_object(path, label="Sol OCR v2 checker artifact")
    _validate_v2_checker_fields(artifact)
    return artifact


def build_checker_v2_artifact(
    raw_checker: dict[str, Any],
    *,
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
) -> dict[str, Any]:
    """Bind a third-session raw verdict to an independently produced A/B pair."""
    required = {
        "sample_id",
        "session_id",
        "worker_id",
        "candidate_coverage",
        "reading_order",
        "major_errors",
        "selection",
        "verdict",
        "reason",
        "checked_at",
    }
    if set(raw_checker) != required:
        raise ValueError("unsupported Sol OCR v2 raw checker fields")
    validate_page_candidate_pair(candidate_a, candidate_b)
    if raw_checker["sample_id"] != candidate_a["sample_id"]:
        raise ValueError("Sol OCR v2 raw checker sample mismatch")
    common_fields = (
        "campaign_id",
        "manifest_sha256",
        "pilot_sha256",
        "purpose",
        "model",
        "prompt_sha256",
        "policy_sha256",
        "sample_id",
        "book_name",
        "page_no",
        "image_sha256",
    )
    body = {
        "schema_version": CHECKER_ARTIFACT_V2_SCHEMA_VERSION,
        **{field: candidate_a[field] for field in common_fields},
        "session_id": raw_checker["session_id"],
        "worker_id": raw_checker["worker_id"],
        "candidate_a_sha256": candidate_a["candidate_sha256"],
        "candidate_b_sha256": candidate_b["candidate_sha256"],
        "candidate_coverage": raw_checker["candidate_coverage"],
        "reading_order": raw_checker["reading_order"],
        "major_errors": raw_checker["major_errors"],
        "selection": raw_checker["selection"],
        "verdict": raw_checker["verdict"],
        "reason": raw_checker["reason"],
        "checked_at": raw_checker["checked_at"],
    }
    artifact = {**body, "checker_sha256": hashlib.sha256(_canonical_json(body)).hexdigest()}
    validate_checker_v2_artifact(artifact, candidate_a=candidate_a, candidate_b=candidate_b)
    return artifact


def validate_checker_v2_artifact(
    artifact: dict[str, Any],
    *,
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
) -> None:
    """Bind a checker to its independent A/B candidates."""
    _validate_v2_checker_fields(artifact)
    validate_page_candidate_pair(candidate_a, candidate_b)
    for field in (
        "campaign_id",
        "manifest_sha256",
        "pilot_sha256",
        "purpose",
        "model",
        "prompt_sha256",
        "policy_sha256",
        "sample_id",
        "book_name",
        "page_no",
        "image_sha256",
    ):
        if artifact[field] != candidate_a[field]:
            raise ValueError(f"Sol OCR v2 checker {field} mismatch")
    if artifact["candidate_a_sha256"] != candidate_a["candidate_sha256"]:
        raise ValueError("Sol OCR v2 checker candidate A digest mismatch")
    if artifact["candidate_b_sha256"] != candidate_b["candidate_sha256"]:
        raise ValueError("Sol OCR v2 checker candidate B digest mismatch")
    for candidate in (candidate_a, candidate_b):
        if artifact["session_id"] == candidate["session_id"]:
            raise ValueError("Sol OCR v2 checker must use a third session")
        if artifact["worker_id"] == candidate["worker_id"]:
            raise ValueError("Sol OCR v2 checker must use a third worker")


def _validate_v2_resolved_fields(artifact: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "campaign_id",
        "manifest_sha256",
        "pilot_sha256",
        "purpose",
        "prompt_sha256",
        "policy_sha256",
        "sample_id",
        "book_name",
        "page_no",
        "image_sha256",
        "candidate_a_sha256",
        "candidate_b_sha256",
        "checker_sha256",
        "canonical_eligible",
        "resolved_at",
        "resolved_sha256",
    }
    if set(artifact) != required:
        raise ValueError("unsupported Sol OCR v2 resolved artifact fields")
    if artifact["schema_version"] != RESOLVED_ARTIFACT_V2_SCHEMA_VERSION:
        raise ValueError("unsupported Sol OCR v2 resolved artifact schema")
    if artifact["purpose"] not in _V2_PURPOSES:
        raise ValueError("unsupported Sol OCR v2 resolved purpose")
    for field in ("campaign_id", "sample_id", "book_name"):
        _validate_non_empty_string(artifact[field], label=f"Sol OCR v2 resolved {field}")
    for field in (
        "manifest_sha256",
        "pilot_sha256",
        "prompt_sha256",
        "policy_sha256",
        "image_sha256",
        "candidate_a_sha256",
        "candidate_b_sha256",
        "checker_sha256",
    ):
        _validate_lower_sha256(artifact[field], label=f"Sol OCR v2 resolved {field}")
    if type(artifact["page_no"]) is not int or artifact["page_no"] < 1:
        raise ValueError("Sol OCR v2 resolved page_no must be a positive integer")
    if type(artifact["canonical_eligible"]) is not bool:
        raise ValueError("Sol OCR v2 resolved canonical_eligible must be a boolean")
    _validate_timestamp(artifact["resolved_at"], label="Sol OCR v2 resolved resolved_at")
    _validate_artifact_digest(artifact, digest_field="resolved_sha256", label="Sol OCR v2 resolved")


def load_resolved_v2_artifact(path: Path) -> dict[str, Any]:
    """Load a self-hashed v2 envelope that references A, B, and checker artifacts."""
    artifact = _load_json_object(path, label="Sol OCR v2 resolved artifact")
    _validate_v2_resolved_fields(artifact)
    return artifact


def build_resolved_v2_artifact(
    *,
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
    checker: dict[str, Any],
    canonical_eligible: bool,
    resolved_at: str,
) -> dict[str, Any]:
    """Create the self-hashed envelope after A/B/checker validation."""
    validate_checker_v2_artifact(checker, candidate_a=candidate_a, candidate_b=candidate_b)
    common_fields = (
        "campaign_id",
        "manifest_sha256",
        "pilot_sha256",
        "purpose",
        "prompt_sha256",
        "policy_sha256",
        "sample_id",
        "book_name",
        "page_no",
        "image_sha256",
    )
    body = {
        "schema_version": RESOLVED_ARTIFACT_V2_SCHEMA_VERSION,
        **{field: candidate_a[field] for field in common_fields},
        "candidate_a_sha256": candidate_a["candidate_sha256"],
        "candidate_b_sha256": candidate_b["candidate_sha256"],
        "checker_sha256": checker["checker_sha256"],
        "canonical_eligible": canonical_eligible,
        "resolved_at": resolved_at,
    }
    artifact = {**body, "resolved_sha256": hashlib.sha256(_canonical_json(body)).hexdigest()}
    _validate_v2_resolved_fields(artifact)
    if canonical_eligible:
        selection = checker["selection"]
        if (
            checker["verdict"] != "pass"
            or selection not in _V2_CANDIDATE_IDS
            or checker["candidate_coverage"][selection] != "complete"
            or checker["reading_order"] != "pass"
            or checker["major_errors"]
        ):
            raise ValueError("Sol OCR v2 resolved canonical eligibility requirements are not met")
    return artifact


def validate_resolved_v2_artifact(
    artifact: dict[str, Any],
    *,
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
    checker: dict[str, Any],
    pilot_manifest: dict[str, Any],
    images_root: Path,
) -> dict[str, Any]:
    """Validate every v2 binding and return the fixed pilot sample.

    `canonical_eligible` is deliberately a narrow assertion: a checker pass,
    selected candidate, complete selected coverage, passing reading order, and
    no major checker errors are all required before it can be true.
    """
    _validate_v2_resolved_fields(artifact)
    sample = validate_page_candidate_v2_artifact(
        candidate_a,
        pilot_manifest=pilot_manifest,
        images_root=images_root,
    )
    second_sample = validate_page_candidate_v2_artifact(
        candidate_b,
        pilot_manifest=pilot_manifest,
        images_root=images_root,
    )
    if sample != second_sample:
        raise ValueError("Sol OCR v2 candidates resolve different pilot samples")
    validate_checker_v2_artifact(checker, candidate_a=candidate_a, candidate_b=candidate_b)
    for field in (
        "campaign_id",
        "manifest_sha256",
        "pilot_sha256",
        "purpose",
        "prompt_sha256",
        "policy_sha256",
        "sample_id",
        "book_name",
        "page_no",
        "image_sha256",
    ):
        if artifact[field] != candidate_a[field]:
            raise ValueError(f"Sol OCR v2 resolved {field} mismatch")
    if artifact["candidate_a_sha256"] != candidate_a["candidate_sha256"]:
        raise ValueError("Sol OCR v2 resolved candidate A digest mismatch")
    if artifact["candidate_b_sha256"] != candidate_b["candidate_sha256"]:
        raise ValueError("Sol OCR v2 resolved candidate B digest mismatch")
    if artifact["checker_sha256"] != checker["checker_sha256"]:
        raise ValueError("Sol OCR v2 resolved checker digest mismatch")
    if artifact["canonical_eligible"]:
        selection = checker["selection"]
        if (
            checker["verdict"] != "pass"
            or selection not in _V2_CANDIDATE_IDS
            or checker["candidate_coverage"][selection] != "complete"
            or checker["reading_order"] != "pass"
            or checker["major_errors"]
        ):
            raise ValueError("Sol OCR v2 resolved canonical eligibility requirements are not met")
    return sample
