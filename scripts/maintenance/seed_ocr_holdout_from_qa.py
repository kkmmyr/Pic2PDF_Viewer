"""Seed a fixed OCR holdout from pre-existing approved Codex corrections."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def _request_json(
    url: str, *, method: str = "GET", payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urlopen(request, timeout=60) as response:  # noqa: S310 - operator API URL
        return json.load(response)


def validate_holdout_page(page: dict[str, Any]) -> None:
    if page.get("qa_state") != "approved":
        raise ValueError("holdout page must already be QA-approved")
    if page.get("page_type") != "narrative":
        raise ValueError("holdout page must be narrative")
    if page.get("layout_type") != "normal_prose":
        raise ValueError("holdout page must be normal_prose")
    if page.get("selected_engine") != "codex":
        raise ValueError("holdout page must use a pre-existing Codex correction")
    if not str(page.get("corrected_text") or "").strip():
        raise ValueError("holdout page must have corrected_text")


def build_run_selection(run_details: dict[int, dict[str, Any]]) -> dict[str, Any]:
    entries = []
    for run_id, detail in sorted(run_details.items()):
        for page in detail["pages"]:
            try:
                validate_holdout_page(page)
            except ValueError:
                continue
            entries.append(
                {
                    "run_id": run_id,
                    "page_no": int(page["page_no"]),
                    "series": str(detail["book_name"]),
                }
            )
    if not entries:
        raise ValueError("selected runs contain no eligible holdout pages")
    return {"name": "B-35 final run-separated holdout", "entries": entries}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--selection", type=Path)
    source.add_argument("--run-id", type=int, action="append")
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.selection is not None:
        selection = json.loads(args.selection.read_text(encoding="utf-8"))
        requested_run_ids = sorted(
            {int(item["run_id"]) for item in selection["entries"]}
        )
    else:
        requested_run_ids = sorted(set(args.run_id or []))
        if len(requested_run_ids) != len(args.run_id or []):
            parser.error("run IDs must not contain duplicates")
        selection = None
    run_details = {
        run_id: _request_json(f"{args.api_base.rstrip('/')}/api/ocr/qa/runs/{run_id}")
        for run_id in requested_run_ids
    }
    if selection is None:
        selection = build_run_selection(run_details)
    selected_entries = selection["entries"]
    validated = []
    for selected in selected_entries:
        run_id = int(selected["run_id"])
        page_no = int(selected["page_no"])
        pages = {int(page["page_no"]): page for page in run_details[run_id]["pages"]}
        page = pages.get(page_no)
        if page is None:
            raise ValueError(f"OCR page not found: run={run_id}, page={page_no}")
        validate_holdout_page(page)
        validated.append(
            {
                **selected,
                "book_name": str(run_details[run_id]["book_name"]),
                "reference_text": str(page["corrected_text"]),
                "reference_chars": len("".join(str(page["corrected_text"]).split())),
            }
        )

    result: dict[str, Any] = {
        "selection_name": selection["name"],
        "validated_count": len(validated),
        "series_count": len({str(item["series"]) for item in validated}),
        "applied": False,
        "entries": [
            {
                key: value
                for key, value in item.items()
                if key not in {"reference_text", "book_name"}
            }
            for item in validated
        ],
    }
    if args.apply:
        _request_json(
            f"{args.api_base.rstrip('/')}/api/ocr/ground-truth/seed",
            method="POST",
            payload={
                "samples": [
                    {"run_id": item["run_id"], "page_no": item["page_no"]}
                    for item in validated
                ]
            },
        )
        ground_truth = _request_json(
            f"{args.api_base.rstrip('/')}/api/ocr/ground-truth"
        )
        ground_truth_by_source = {
            (int(entry["run_id"]), int(entry["page_no"])): entry
            for entry in ground_truth["entries"]
        }
        applied_entries = []
        for item in validated:
            source_key = (int(item["run_id"]), int(item["page_no"]))
            entry = ground_truth_by_source.get(source_key)
            if entry is None:
                raise RuntimeError(f"seeded ground-truth entry missing: {source_key}")
            already_verified = (
                entry.get("state") == "verified"
                and str(entry.get("reference_text") or "")
                == str(item["reference_text"])
                and entry.get("page_type") == "narrative"
                and entry.get("layout_type") == "normal_prose"
            )
            if not already_verified:
                _request_json(
                    f"{args.api_base.rstrip('/')}/api/ocr/ground-truth/{entry['id']}",
                    method="PATCH",
                    payload={
                        "reference_text": item["reference_text"],
                        "page_type": "narrative",
                        "layout_type": "normal_prose",
                        "state": "verified",
                        "note": (
                            "B-35 holdout; pre-existing approved Codex image-QA correction; "
                            f"series={item['series']}; fixed before gap-consensus evaluation"
                        ),
                    },
                )
            applied_entries.append(
                {
                    "id": int(entry["id"]),
                    "run_id": item["run_id"],
                    "page_no": item["page_no"],
                    "series": item["series"],
                    "image_sha256": str(entry["image_sha256"]),
                    "reference_chars": item["reference_chars"],
                }
            )
        result["applied"] = True
        result["entries"] = applied_entries

    print(
        f"validated={result['validated_count']}, series={result['series_count']}, "
        f"applied={result['applied']}"
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
