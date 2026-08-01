"""Inventory approved Codex OCR corrections for an isolated fine-tuning pilot.

The report intentionally contains counts and metadata only. Corrected text and
page images must stay in the operator environment and must not be written to the
audit JSON or committed to Git.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def _request_json(url: str) -> dict[str, Any]:
    request = Request(url, method="GET")
    with urlopen(request, timeout=60) as response:  # noqa: S310 - operator API URL
        return json.load(response)


def is_eligible_page(page: dict[str, Any]) -> bool:
    """Return whether a page is a verified normal-prose correction candidate."""

    return (
        page.get("qa_state") == "approved"
        and page.get("page_type") == "narrative"
        and page.get("layout_type") == "normal_prose"
        and page.get("selected_engine") == "codex"
        and bool(str(page.get("corrected_text") or "").strip())
    )


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    eligible_pages = [page for page in run.get("pages", []) if is_eligible_page(page)]
    return {
        "run_id": int(run["id"]),
        "book_name": str(run["book_name"]),
        "eligible_pages": len(eligible_pages),
        "reference_chars": sum(
            len("".join(str(page["corrected_text"]).split()))
            for page in eligible_pages
        ),
    }


def _split_summary(runs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(runs, key=lambda item: int(item["run_id"]))
    return {
        "run_count": len(ordered),
        "eligible_pages": sum(int(item["eligible_pages"]) for item in ordered),
        "reference_chars": sum(int(item["reference_chars"]) for item in ordered),
        "runs": ordered,
    }


def build_inventory(
    run_details: Iterable[dict[str, Any]], *, holdout_run_ids: set[int]
) -> dict[str, Any]:
    """Build a text-free train/holdout inventory with run-level isolation."""

    summaries = [
        _run_summary(run)
        for run in run_details
        if run.get("state") == "completed" and run.get("qa_state") == "approved"
    ]
    summaries = [item for item in summaries if item["eligible_pages"] > 0]
    available_ids = {int(item["run_id"]) for item in summaries}
    missing_holdout = holdout_run_ids - available_ids
    if missing_holdout:
        missing = ", ".join(str(run_id) for run_id in sorted(missing_holdout))
        raise ValueError(f"holdout runs have no eligible pages: {missing}")

    holdout = [
        item for item in summaries if int(item["run_id"]) in holdout_run_ids
    ]
    training = [
        item for item in summaries if int(item["run_id"]) not in holdout_run_ids
    ]
    overlap = {int(item["run_id"]) for item in training} & {
        int(item["run_id"]) for item in holdout
    }
    if overlap:
        raise RuntimeError(f"train/holdout run overlap: {sorted(overlap)}")

    return {
        "filters": {
            "run_state": "completed",
            "run_qa_state": "approved",
            "page_qa_state": "approved",
            "page_type": "narrative",
            "layout_type": "normal_prose",
            "selected_engine": "codex",
            "corrected_text": "non-empty",
        },
        "isolation_unit": "ocr_run",
        "contains_page_text": False,
        "contains_page_images": False,
        "training": _split_summary(training),
        "holdout": _split_summary(holdout),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--holdout-run-id", action="append", type=int, required=True)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    api_base = args.api_base.rstrip("/")
    run_list = _request_json(f"{api_base}/api/ocr/qa/runs")["runs"]
    approved_ids = [
        int(run["id"])
        for run in run_list
        if run.get("state") == "completed" and run.get("qa_state") == "approved"
    ]
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        run_details = list(
            executor.map(
                lambda run_id: _request_json(f"{api_base}/api/ocr/qa/runs/{run_id}"),
                approved_ids,
            )
        )

    result = build_inventory(
        run_details, holdout_run_ids=set(args.holdout_run_id)
    )
    result["generated_at"] = datetime.now(UTC).isoformat()
    result["api_base"] = api_base
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        "training="
        f"{result['training']['eligible_pages']} pages/"
        f"{result['training']['reference_chars']} chars; "
        "holdout="
        f"{result['holdout']['eligible_pages']} pages/"
        f"{result['holdout']['reference_chars']} chars"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
