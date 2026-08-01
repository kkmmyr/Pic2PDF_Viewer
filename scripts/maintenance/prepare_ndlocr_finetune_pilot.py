"""Create a fail-closed NDLOCR PARSeq line-crop pilot dataset.

The output directory contains copyrighted page crops and corrected labels and
must remain local/ignored. ``--audit-output`` receives counts and hashes only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
import unicodedata
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from PIL import Image

_DASH_TRANSLATION = str.maketrans({dash: "―" for dash in "‐‑‒–—―"})


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05 * (attempt + 1))


def validate_resume_state(
    state: dict[str, Any],
    *,
    run_ids: list[int],
    holdout_run_ids: list[int],
    pages_per_run: int,
    images_dir: Path,
    labels_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if state.get("format_version") != 1:
        raise ValueError("unsupported resume state format")
    expected = {
        "run_ids": run_ids,
        "holdout_run_ids": holdout_run_ids,
        "pages_per_run": pages_per_run,
    }
    mismatches = {
        key: {"actual": state.get(key), "expected": value}
        for key, value in expected.items()
        if state.get(key) != value
    }
    if mismatches:
        raise ValueError(f"resume state arguments differ: {mismatches}")
    samples = state.get("samples")
    pages = state.get("pages")
    if not isinstance(samples, list) or not isinstance(pages, list):
        raise ValueError("resume state samples/pages are invalid")
    page_keys = [(int(item["run_id"]), int(item["page_no"])) for item in pages]
    if len(page_keys) != len(set(page_keys)):
        raise ValueError("resume state contains duplicate pages")
    forbidden = set(holdout_run_ids) & {run_id for run_id, _page_no in page_keys}
    if forbidden:
        raise ValueError(
            f"resume state contains final holdout runs: {sorted(forbidden)}"
        )
    completed_keys = set(page_keys)
    for sample in samples:
        key = (int(sample["run_id"]), int(sample["page_no"]))
        if key not in completed_keys:
            raise ValueError(f"resume sample has no completed page: {key}")
        image_path = Path(str(sample["image"])).resolve()
        if image_path.parent != images_dir.resolve() or not image_path.is_file():
            raise ValueError(
                f"resume sample image is missing or outside output: {image_path}"
            )
        label_path = labels_dir.resolve() / f"{image_path.stem}.txt"
        if not label_path.is_file():
            raise ValueError(f"resume sample label is missing: {label_path}")
        if label_path.read_text(encoding="utf-8") != str(sample["label"]):
            raise ValueError(f"resume sample label differs: {label_path}")
    return samples, pages


def _write_progress(
    *,
    resume_path: Path,
    private_manifest_path: Path,
    audit_output: Path,
    run_ids: list[int],
    holdout_run_ids: list[int],
    pages_per_run: int,
    samples: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> None:
    generated_at = datetime.now(UTC).isoformat()
    state = {
        "format_version": 1,
        "updated_at": generated_at,
        "run_ids": run_ids,
        "holdout_run_ids": holdout_run_ids,
        "pages_per_run": pages_per_run,
        "samples": samples,
        "pages": pages,
    }
    _write_json_atomic(resume_path, state)
    _write_json_atomic(
        private_manifest_path,
        {"created_at": generated_at, "samples": samples},
    )
    _write_json_atomic(
        audit_output,
        {
            "generated_at": generated_at,
            "contains_page_text": False,
            "contains_page_images": False,
            "pilot_run_ids": run_ids,
            "excluded_holdout_run_ids": holdout_run_ids,
            "page_count": len(pages),
            "accepted_segments": len(samples),
            "accepted_label_chars": sum(int(item["label_chars"]) for item in samples),
            "pages": pages,
        },
    )


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).translate(_DASH_TRANSLATION)
    normalized = normalized.replace("...", "…")
    return re.sub(r"\s+", "", normalized)


def _edit_alignment(
    reference: str, hypothesis: str
) -> tuple[int, list[tuple[int, int]]]:
    """Return Levenshtein distance and one deterministic forward state path."""

    row_count = len(reference)
    column_count = len(hypothesis)
    directions = [bytearray(column_count + 1) for _ in range(row_count + 1)]
    for column_index in range(1, column_count + 1):
        directions[0][column_index] = 3
    previous = list(range(column_count + 1))
    for row_index, reference_char in enumerate(reference, start=1):
        current = [row_index]
        directions[row_index][0] = 2
        for column_index, hypothesis_char in enumerate(hypothesis, start=1):
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

    states = [(row_count, column_count)]
    row_index = row_count
    column_index = column_count
    while row_index or column_index:
        direction = directions[row_index][column_index]
        if direction == 1:
            row_index -= 1
            column_index -= 1
        elif direction == 2:
            row_index -= 1
        else:
            column_index -= 1
        states.append((row_index, column_index))
    states.reverse()
    return previous[column_count], states


def align_segment_labels(
    reference_text: str,
    segment_texts: list[str],
    *,
    max_page_cer: float = 0.15,
    max_segment_cer: float = 0.15,
    min_label_chars: int = 5,
    max_label_chars: int = 100,
    max_boundary_gap: int = 0,
) -> dict[str, Any]:
    """Map a corrected page transcription to OCR segments without guessing."""

    reference = normalize_text(reference_text)
    normalized_segments = [normalize_text(text) for text in segment_texts]
    hypothesis = "".join(normalized_segments)
    if not reference or not hypothesis:
        return {"accepted": [], "rejected": [], "reason": "empty_page_text"}
    distance, states = _edit_alignment(reference, hypothesis)
    page_cer = distance / len(reference)
    if page_cer > max_page_cer:
        return {
            "accepted": [],
            "rejected": list(range(len(segment_texts))),
            "reason": "page_cer_exceeded",
            "page_cer": page_cer,
        }

    reference_positions: dict[int, list[int]] = {}
    for reference_index, hypothesis_index in states:
        reference_positions.setdefault(hypothesis_index, []).append(reference_index)
    hypothesis_boundaries = [0]
    for segment in normalized_segments:
        hypothesis_boundaries.append(hypothesis_boundaries[-1] + len(segment))

    reference_boundaries = [0]
    ambiguous_boundaries: set[int] = set()
    for boundary_index, hypothesis_index in enumerate(
        hypothesis_boundaries[1:-1], start=1
    ):
        positions = reference_positions.get(hypothesis_index, [])
        if not positions:
            ambiguous_boundaries.add(boundary_index)
            reference_boundaries.append(reference_boundaries[-1])
            continue
        if max(positions) - min(positions) > max_boundary_gap:
            ambiguous_boundaries.add(boundary_index)
        reference_boundaries.append((min(positions) + max(positions)) // 2)
    reference_boundaries.append(len(reference))

    accepted = []
    rejected = []
    for index, segment in enumerate(normalized_segments):
        label = reference[reference_boundaries[index] : reference_boundaries[index + 1]]
        reasons = []
        if index in ambiguous_boundaries or index + 1 in ambiguous_boundaries:
            reasons.append("ambiguous_boundary")
        if not min_label_chars <= len(label) <= max_label_chars:
            reasons.append("label_length")
        segment_distance, _ = _edit_alignment(label, segment)
        segment_cer = segment_distance / len(label) if label else None
        if segment_cer is None or segment_cer > max_segment_cer:
            reasons.append("segment_cer_exceeded")
        item = {
            "segment_index": index,
            "label": label,
            "label_chars": len(label),
            "segment_cer": segment_cer,
            "reasons": reasons,
        }
        (rejected if reasons else accepted).append(item)
    return {
        "accepted": accepted,
        "rejected": rejected,
        "reason": None,
        "page_cer": page_cer,
    }


def _request_json(url: str) -> dict[str, Any]:
    request = Request(url, method="GET")
    with urlopen(request, timeout=60) as response:  # noqa: S310 - operator API URL
        return json.load(response)


def _download(url: str) -> bytes:
    with urlopen(url, timeout=60) as response:  # noqa: S310 - operator API URL
        return response.read()


def _is_eligible_page(page: dict[str, Any]) -> bool:
    return (
        page.get("qa_state") == "approved"
        and page.get("page_type") == "narrative"
        and page.get("layout_type") == "normal_prose"
        and page.get("selected_engine") == "codex"
        and bool(str(page.get("corrected_text") or "").strip())
    )


def select_evenly(pages: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count < 1 or not pages:
        return []
    if len(pages) <= count:
        return pages
    if count == 1:
        return [pages[len(pages) // 2]]
    indexes = {round(index * (len(pages) - 1) / (count - 1)) for index in range(count)}
    return [pages[index] for index in sorted(indexes)]


def _flatten_contents(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_flatten_contents(item))
        return result
    return []


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")


def parse_ndlocr_segments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    segments = []
    for line in _flatten_contents(payload.get("contents", [])):
        text = str(line.get("text") or "").strip()
        bbox = line.get("boundingBox")
        if not text or not _truthy(line.get("isTextline", True)):
            continue
        if not isinstance(bbox, list) or not bbox:
            continue
        points = [
            point
            for point in bbox
            if isinstance(point, list)
            and len(point) >= 2
            and all(isinstance(value, (int, float)) for value in point[:2])
        ]
        if not points:
            continue
        is_vertical = _truthy(line.get("isVertical"))
        if not is_vertical:
            continue
        segments.append(
            {
                "text": text,
                "bbox": points,
                "center_x": sum(float(point[0]) for point in points) / len(points),
                "center_y": sum(float(point[1]) for point in points) / len(points),
            }
        )
    segments.sort(key=lambda item: (-item["center_x"], item["center_y"]))
    for segment in segments:
        segment.pop("center_x")
        segment.pop("center_y")
    return segments


def _crop_segment(
    image: Image.Image, bbox: list[list[float]], *, margin: int
) -> Image.Image:
    xs = [float(point[0]) for point in bbox]
    ys = [float(point[1]) for point in bbox]
    left = max(0, int(min(xs)) - margin)
    top = max(0, int(min(ys)) - margin)
    right = min(image.width, int(max(xs)) + margin + 1)
    bottom = min(image.height, int(max(ys)) + margin + 1)
    if right <= left or bottom <= top:
        raise ValueError("invalid segment bbox")
    crop = image.crop((left, top, right, bottom)).convert("RGB")
    if crop.height > crop.width:
        crop = crop.transpose(Image.Transpose.ROTATE_90)
    return crop


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--run-id", action="append", type=int, required=True)
    parser.add_argument("--holdout-run-id", action="append", type=int, default=[])
    parser.add_argument("--pages-per-run", type=int, default=5)
    parser.add_argument("--ndlocr-python", type=Path, required=True)
    parser.add_argument("--ndlocr-script", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--margin", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    overlap = set(args.run_id) & set(args.holdout_run_id)
    if overlap:
        parser.error(f"run IDs overlap final holdout: {sorted(overlap)}")
    api_base = args.api_base.rstrip("/")
    args.output_dir = args.output_dir.resolve()
    args.audit_output = args.audit_output.resolve()
    args.ndlocr_python = args.ndlocr_python.resolve()
    args.ndlocr_script = args.ndlocr_script.resolve()
    if len(args.run_id) != len(set(args.run_id)):
        parser.error("run IDs must not contain duplicates")
    if len(args.holdout_run_id) != len(set(args.holdout_run_id)):
        parser.error("holdout run IDs must not contain duplicates")
    resume_path = args.output_dir / "resume-state.json"
    private_manifest_path = args.output_dir / "private-manifest.json"
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.resume:
        parser.error("output directory is not empty; use --resume after validation")
    if args.resume and not resume_path.is_file():
        parser.error("--resume requires resume-state.json")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = args.output_dir / "images"
    labels_dir = args.output_dir / "labels"
    work_dir = args.output_dir / "work"
    for directory in (images_dir, labels_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)

    if args.resume:
        private_samples, audit_pages = validate_resume_state(
            json.loads(resume_path.read_text(encoding="utf-8")),
            run_ids=args.run_id,
            holdout_run_ids=args.holdout_run_id,
            pages_per_run=args.pages_per_run,
            images_dir=images_dir,
            labels_dir=labels_dir,
        )
        _write_progress(
            resume_path=resume_path,
            private_manifest_path=private_manifest_path,
            audit_output=args.audit_output,
            run_ids=args.run_id,
            holdout_run_ids=args.holdout_run_id,
            pages_per_run=args.pages_per_run,
            samples=private_samples,
            pages=audit_pages,
        )
    else:
        private_samples = []
        audit_pages = []
    completed_pages = {
        (int(item["run_id"]), int(item["page_no"])): item for item in audit_pages
    }
    intended_page_keys: set[tuple[int, int]] = set()
    for run_id in args.run_id:
        detail = _request_json(f"{api_base}/api/ocr/qa/runs/{run_id}")
        if detail.get("state") != "completed" or detail.get("qa_state") != "approved":
            raise ValueError(f"run {run_id} is not completed and approved")
        pages = select_evenly(
            [page for page in detail["pages"] if _is_eligible_page(page)],
            args.pages_per_run,
        )
        run_output = work_dir / f"run-{run_id:04d}-ndlocr-json"
        run_output.mkdir(exist_ok=True)
        pending_pages: list[dict[str, Any]] = []
        for page in pages:
            page_no = int(page["page_no"])
            page_key = (run_id, page_no)
            intended_page_keys.add(page_key)
            stem = f"r{run_id:04d}-p{page_no:04d}"
            page_bytes = _download(
                urljoin(f"{api_base}/", str(page["image_url"]).lstrip("/"))
            )
            image_sha256 = hashlib.sha256(page_bytes).hexdigest()
            if page_key in completed_pages:
                if completed_pages[page_key].get("image_sha256") != image_sha256:
                    raise ValueError(
                        f"source image changed for completed page {page_key}"
                    )
                continue
            page_path = work_dir / f"{stem}.png"
            page_path.write_bytes(page_bytes)
            pending_pages.append(
                {
                    "page": page,
                    "page_no": page_no,
                    "page_key": page_key,
                    "stem": stem,
                    "page_path": page_path,
                    "image_sha256": image_sha256,
                    "json_path": run_output / f"{stem}.json",
                    "sha_path": run_output / f"{stem}.sha256",
                }
            )

        missing_ocr = [
            item
            for item in pending_pages
            if not item["json_path"].is_file()
            or not item["sha_path"].is_file()
            or item["sha_path"].read_text(encoding="ascii").strip()
            != item["image_sha256"]
        ]
        if missing_ocr:
            batch_input = work_dir / f"run-{run_id:04d}-input-{uuid.uuid4().hex}"
            batch_input.mkdir()
            for item in missing_ocr:
                shutil.copy2(item["page_path"], batch_input / f"{item['stem']}.png")
            result = subprocess.run(
                [
                    str(args.ndlocr_python),
                    str(args.ndlocr_script),
                    "--sourcedir",
                    str(batch_input),
                    "--output",
                    str(run_output),
                    "--json-only",
                ],
                cwd=args.ndlocr_script.parent.parent,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            missing_outputs = [
                str(item["json_path"])
                for item in missing_ocr
                if not item["json_path"].is_file()
            ]
            if missing_outputs:
                raise RuntimeError(
                    f"NDLOCR JSON outputs are missing: {missing_outputs}; "
                    f"stdout={result.stdout!r}; stderr={result.stderr!r}"
                )
            for item in missing_ocr:
                item["sha_path"].write_text(item["image_sha256"], encoding="ascii")

        for pending in pending_pages:
            page = pending["page"]
            page_no = int(pending["page_no"])
            page_key = pending["page_key"]
            stem = str(pending["stem"])
            page_path = pending["page_path"]
            image_sha256 = str(pending["image_sha256"])
            segments = parse_ndlocr_segments(
                json.loads(pending["json_path"].read_text(encoding="utf-8"))
            )
            alignment = align_segment_labels(
                str(page["corrected_text"]),
                [str(segment["text"]) for segment in segments],
            )
            image = Image.open(page_path).convert("RGB")
            accepted_indexes = {
                int(item["segment_index"]): item for item in alignment["accepted"]
            }
            page_samples = []
            for segment_index, item in accepted_indexes.items():
                sample_stem = f"{stem}-s{segment_index:03d}"
                crop = _crop_segment(
                    image, segments[segment_index]["bbox"], margin=args.margin
                )
                image_path = images_dir / f"{sample_stem}.jpg"
                label_path = labels_dir / f"{sample_stem}.txt"
                crop.save(image_path, format="JPEG", quality=95)
                label_path.write_text(str(item["label"]), encoding="utf-8")
                page_samples.append(
                    {
                        "run_id": run_id,
                        "page_no": page_no,
                        "segment_index": segment_index,
                        "image": str(image_path.resolve()),
                        "label": str(item["label"]),
                        "label_chars": int(item["label_chars"]),
                        "segment_cer": item["segment_cer"],
                    }
                )
            audit_page = {
                "run_id": run_id,
                "page_no": page_no,
                "image_sha256": image_sha256,
                "detected_segments": len(segments),
                "accepted_segments": len(alignment["accepted"]),
                "rejected_segments": len(alignment["rejected"]),
                "page_cer": alignment.get("page_cer"),
                "page_rejection_reason": alignment.get("reason"),
            }
            private_samples.extend(page_samples)
            audit_pages.append(audit_page)
            completed_pages[page_key] = audit_page
            _write_progress(
                resume_path=resume_path,
                private_manifest_path=private_manifest_path,
                audit_output=args.audit_output,
                run_ids=args.run_id,
                holdout_run_ids=args.holdout_run_id,
                pages_per_run=args.pages_per_run,
                samples=private_samples,
                pages=audit_pages,
            )

    completed_page_keys = set(completed_pages)
    if completed_page_keys != intended_page_keys:
        raise ValueError(
            "completed pages differ from current eligible selection: "
            f"extra={sorted(completed_page_keys - intended_page_keys)}, "
            f"missing={sorted(intended_page_keys - completed_page_keys)}"
        )
    _write_progress(
        resume_path=resume_path,
        private_manifest_path=private_manifest_path,
        audit_output=args.audit_output,
        run_ids=args.run_id,
        holdout_run_ids=args.holdout_run_id,
        pages_per_run=args.pages_per_run,
        samples=private_samples,
        pages=audit_pages,
    )
    print(
        f"pages={len(audit_pages)}, accepted_segments={len(private_samples)}, "
        f"accepted_chars={sum(int(item['label_chars']) for item in private_samples)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
