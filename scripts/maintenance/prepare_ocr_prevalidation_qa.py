"""Prepare a private, read-only OCR candidate disagreement queue.

The generated package contains copyrighted OCR text and page images. Keep it
under an ignored audit directory. This command never updates OCR QA or public
book data.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

_MERGE_PATH = Path(__file__).with_name("merge_ocr_consensus_gaps.py")
_SPEC = importlib.util.spec_from_file_location("ocr_gap_merge", _MERGE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"could not load OCR gap merge module: {_MERGE_PATH}")
gap_merge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gap_merge)


def _request_json(url: str) -> dict[str, Any]:
    request = Request(url, method="GET")
    with urlopen(request, timeout=60) as response:  # noqa: S310 - operator API
        return json.load(response)


def _normalize(text: str) -> str:
    return "".join(text.split())


def candidate_similarity(primary: str, external: str) -> float:
    normalized_primary = _normalize(primary)
    normalized_external = _normalize(external)
    if not normalized_primary and not normalized_external:
        return 1.0
    return difflib.SequenceMatcher(
        None,
        normalized_primary,
        normalized_external,
        autojunk=False,
    ).ratio()


def validate_selected_page(page: dict[str, Any]) -> None:
    if page.get("qa_state") != "approved":
        raise ValueError("prevalidation page must already be QA-approved")
    if page.get("page_type") != "narrative":
        raise ValueError("prevalidation page must be narrative")
    if page.get("layout_type") != "normal_prose":
        raise ValueError("prevalidation page must be normal_prose")


def build_priority_queue(
    package_items: Sequence[dict[str, Any]],
    merge_pages: Sequence[dict[str, Any]],
    *,
    similarity_threshold: float,
) -> list[dict[str, Any]]:
    merges = {
        (int(item["run_id"]), int(item["page_no"])): item for item in merge_pages
    }
    queue = []
    for item in package_items:
        key = (int(item["run_id"]), int(item["page_no"]))
        merge = merges[key]
        reasons = []
        similarity = float(item["candidate_similarity"])
        if similarity < similarity_threshold:
            reasons.append("candidate_similarity_below_threshold")
        if int(merge["proposal_count"]) > 0:
            reasons.append("anchored_gap_proposal")
        if not reasons:
            continue
        queue.append(
            {
                "run_id": key[0],
                "page_no": key[1],
                "image_sha256": str(item["image_sha256"]),
                "candidate_similarity": similarity,
                "proposal_count": int(merge["proposal_count"]),
                "reasons": reasons,
            }
        )
    queue.sort(
        key=lambda item: (
            float(item["candidate_similarity"]),
            -int(item["proposal_count"]),
        )
    )
    return queue


def queue_identity_sha256(queue: Sequence[dict[str, Any]]) -> str:
    """Return a stable identity for the exact page/image set handed to QA."""
    identity = [
        {
            "run_id": int(item["run_id"]),
            "page_no": int(item["page_no"]),
            "image_sha256": str(item["image_sha256"]),
        }
        for item in queue
    ]
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_queue_document(document: dict[str, Any]) -> dict[str, Any]:
    """Verify the embedded count and identity without touching external state."""
    queue = document.get("queue")
    if not isinstance(queue, list):
        raise ValueError("QA queue document must contain a queue list")
    actual_count = len(queue)
    expected_count = int(document.get("queue_count", -1))
    if expected_count != actual_count:
        raise ValueError(
            f"QA queue count mismatch: expected={expected_count}, actual={actual_count}"
        )
    actual_identity = queue_identity_sha256(queue)
    expected_identity = str(document.get("queue_identity_sha256") or "")
    if expected_identity != actual_identity:
        raise ValueError(
            "QA queue identity mismatch: "
            f"expected={expected_identity}, actual={actual_identity}"
        )
    return {
        "queue_count": actual_count,
        "queue_identity_sha256": actual_identity,
    }


def prepare_package(
    selection: dict[str, Any],
    *,
    api_base: str,
    output_dir: Path,
    similarity_threshold: float,
    min_gap_chars: int,
    max_gap_chars: int,
    anchor_chars: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)
    requested_run_ids = sorted(
        {int(item["run_id"]) for item in selection["entries"]}
    )
    runs = {
        run_id: _request_json(f"{api_base.rstrip('/')}/api/ocr/qa/runs/{run_id}")
        for run_id in requested_run_ids
    }
    package_items = []
    merge_pages = []
    for selected in selection["entries"]:
        run_id = int(selected["run_id"])
        page_no = int(selected["page_no"])
        pages = {
            int(page["page_no"]): page for page in runs[run_id].get("pages", [])
        }
        page = pages.get(page_no)
        if page is None:
            raise ValueError(f"OCR page not found: run={run_id}, page={page_no}")
        validate_selected_page(page)
        image_path = images_dir / f"r{run_id:04d}-p{page_no:04d}.png"
        if not image_path.is_file():
            image_url = (
                f"{api_base.rstrip('/')}/api/ocr/qa/runs/"
                f"{run_id}/pages/{page_no}/image"
            )
            with urlopen(Request(image_url, method="GET"), timeout=60) as response:  # noqa: S310
                image_path.write_bytes(response.read())
        image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
        primary = str(page.get("primary_text") or "")
        external = str(page.get("external_text") or "")
        similarity = candidate_similarity(primary, external)
        package_items.append(
            {
                "run_id": run_id,
                "page_no": page_no,
                "book_name": str(runs[run_id]["book_name"]),
                "image_path": str(image_path.resolve()),
                "image_sha256": image_sha256,
                "primary_text": primary,
                "external_text": external,
                "selected_engine": page.get("selected_engine"),
                "candidate_similarity": similarity,
                "primary_chars": len(_normalize(primary)),
                "external_chars": len(_normalize(external)),
                "corrected_text": page.get("corrected_text"),
            }
        )
        merged, proposals = gap_merge.merge_supported_gaps(
            primary,
            [("external", external)],
            min_support=1,
            min_chars=min_gap_chars,
            max_chars=max_gap_chars,
            anchor_chars=anchor_chars,
        )
        merge_pages.append(
            {
                "run_id": run_id,
                "page_no": page_no,
                "image_sha256": image_sha256,
                "base": "primary",
                "proposal_count": len(proposals),
                "proposals": proposals,
                "merged_text": merged,
            }
        )

    queue = build_priority_queue(
        package_items,
        merge_pages,
        similarity_threshold=similarity_threshold,
    )
    common = {"diagnostic_only": True, "publishes_ocr": False}
    package = {
        **common,
        "selection_name": selection["name"],
        "items": package_items,
    }
    merges = {
        **common,
        "policy": {
            "base": "primary",
            "alternative": "external",
            "min_support": 1,
            "min_chars": min_gap_chars,
            "max_chars": max_gap_chars,
            "anchor_chars": anchor_chars,
            "requires_image_qa": True,
        },
        "pages": merge_pages,
    }
    priority = {
        **common,
        "queue_count": len(queue),
        "queue_identity_sha256": queue_identity_sha256(queue),
        "criteria": {
            "candidate_similarity_below": similarity_threshold,
            "anchored_gap_proposal_min": 1,
        },
        "queue": queue,
    }
    (output_dir / "qa-package-private.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "anchored-merge-proposals-private.json").write_text(
        json.dumps(merges, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "qa-queue.json").write_text(
        json.dumps(priority, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"pages": len(package_items), "priority_pages": len(queue)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--selection", type=Path)
    source.add_argument("--verify-queue", type=Path)
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--similarity-threshold", type=float, default=0.94)
    parser.add_argument("--min-gap-chars", type=int, default=4)
    parser.add_argument("--max-gap-chars", type=int, default=500)
    parser.add_argument("--anchor-chars", type=int, default=8)
    args = parser.parse_args(argv)
    if args.verify_queue is not None:
        if args.output_dir is not None:
            parser.error("--output-dir cannot be used with --verify-queue")
        verified = verify_queue_document(
            json.loads(args.verify_queue.read_text(encoding="utf-8"))
        )
        print(
            f"queue_count={verified['queue_count']}, "
            f"queue_identity_sha256={verified['queue_identity_sha256']}"
        )
        return 0
    if args.output_dir is None:
        parser.error("--output-dir is required with --selection")
    result = prepare_package(
        json.loads(args.selection.read_text(encoding="utf-8")),
        api_base=args.api_base,
        output_dir=args.output_dir,
        similarity_threshold=args.similarity_threshold,
        min_gap_chars=args.min_gap_chars,
        max_gap_chars=args.max_gap_chars,
        anchor_chars=args.anchor_chars,
    )
    print(f"pages={result['pages']}, priority_pages={result['priority_pages']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
