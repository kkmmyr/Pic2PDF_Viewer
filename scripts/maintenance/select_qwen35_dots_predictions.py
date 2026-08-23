"""Select review-assisted Qwen3.5 OCR or dots.mocr without ground truth.

Both candidates must cover the exact same pages. Qwen remains primary unless
its output has a candidate-only failure signal, or non-repeating dots text is
materially more complete under the production length predicate. Both texts and
their provenance are retained for mandatory image review. The selected text is
only the reviewer's initial candidate; it is not approved for publication.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_ROOT_DIR = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _ROOT_DIR / "backend"
_MAINTENANCE_DIR = Path(__file__).resolve().parent
for _import_path in (_BACKEND_DIR, _MAINTENANCE_DIR):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

from qwen35_ocr_jp_vertical_predict import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    fallback_markup_tags,
    has_suspicious_vertical_bbox_order,
)

from services.novel_db.ocr_candidate_selection import (  # noqa: E402
    is_external_materially_more_complete,
)
from services.novel_db.ocr_content_guards import (  # noqa: E402
    has_suspicious_repetition,
)


def _load_predictions(path: Path, *, source: str) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"{source} prediction file is missing: {path}")
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source} line {line_number} is invalid JSON: {exc.msg}") from exc
            if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                raise ValueError(f"{source} line {line_number} has no string id")
            record_id = record["id"]
            if record_id in records:
                raise ValueError(f"{source} contains duplicate id: {record_id}")
            if not isinstance(record.get("pred"), str) or not record["pred"].strip():
                raise ValueError(f"{source} id {record_id} has an empty prediction")
            records[record_id] = record
    return records


def _require_provenance(record: Mapping[str, Any], *, source: str) -> None:
    record_id = record.get("id")
    for field in (
        "input_sha256",
        "model_revision",
        "model_fingerprint",
        "prompt_id",
    ):
        if not isinstance(record.get(field), str) or not record[field]:
            raise ValueError(f"{source} id {record_id} has no {field}")


def _provenance_signature(record: Mapping[str, Any], *, source: str) -> tuple[str, str, str]:
    _require_provenance(record, source=source)
    return (
        str(record["model_revision"]),
        str(record["model_fingerprint"]),
        str(record["prompt_id"]),
    )


def select_predictions(
    *,
    qwen_path: Path,
    dots_path: Path,
) -> list[dict[str, Any]]:
    qwen = _load_predictions(qwen_path, source="qwen")
    if not qwen:
        raise ValueError("qwen prediction scope is empty")
    dots = _load_predictions(dots_path, source="dots")
    missing = sorted(set(qwen) - set(dots))
    extra = sorted(set(dots) - set(qwen))
    if missing:
        raise ValueError(f"dots predictions are missing qwen ids: {missing[:20]}")
    if extra:
        raise ValueError(f"dots predictions contain non-qwen ids: {extra[:20]}")
    qwen_signatures = {_provenance_signature(record, source="qwen") for record in qwen.values()}
    dots_signatures = {_provenance_signature(record, source="dots") for record in dots.values()}
    if len(qwen_signatures) != 1:
        raise ValueError("qwen predictions mix model or prompt provenance")
    if len(dots_signatures) != 1:
        raise ValueError("dots predictions mix model or prompt provenance")

    fallback_ids: set[str] = set()
    reasons: dict[str, str] = {}
    for record_id, record in qwen.items():
        dots_record = dots[record_id]
        if dots_record["input_sha256"] != record["input_sha256"]:
            raise ValueError(f"dots id {record_id} input_sha256 mismatch")
        if not isinstance(record.get("html_truncated"), bool):
            raise ValueError(f"qwen id {record_id} has no html_truncated flag")
        if not isinstance(record.get("suspicious_repetition"), bool):
            raise ValueError(f"qwen id {record_id} has no suspicious_repetition flag")
        recomputed_repetition = has_suspicious_repetition(record["pred"])
        if record["suspicious_repetition"] != recomputed_repetition:
            raise ValueError(f"qwen id {record_id} repetition flag mismatch")
        raw_response = record.get("raw_response")
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise ValueError(f"qwen id {record_id} has no raw_response")
        markup_tags = fallback_markup_tags(raw_response)
        bbox_order_suspicious = has_suspicious_vertical_bbox_order(raw_response)
        stored_tags = record.get("fallback_markup_tags")
        if stored_tags is not None and stored_tags != list(markup_tags):
            raise ValueError(f"qwen id {record_id} fallback markup mismatch")
        flags = []
        if recomputed_repetition:
            flags.append("suspicious_repetition")
        if record["html_truncated"]:
            flags.append("html_truncated")
        if markup_tags:
            flags.append(f"unsupported_markup:{','.join(markup_tags)}")
        stored_bbox_order = record.get("suspicious_vertical_bbox_order")
        if stored_bbox_order is not None and stored_bbox_order != bbox_order_suspicious:
            raise ValueError(f"qwen id {record_id} bbox order flag mismatch")
        if bbox_order_suspicious:
            flags.append("suspicious_vertical_bbox_order")
        if flags:
            fallback_ids.add(record_id)
            reasons[record_id] = "+".join(flags)
        elif not has_suspicious_repetition(dots_record["pred"]) and is_external_materially_more_complete(
            record["pred"], dots_record["pred"]
        ):
            fallback_ids.add(record_id)
            reasons[record_id] = "dots_materially_more_complete"

    selected: list[dict[str, Any]] = []
    for record_id, qwen_record in qwen.items():
        use_fallback = record_id in fallback_ids
        chosen = dots[record_id] if use_fallback else qwen_record
        if use_fallback:
            if has_suspicious_repetition(chosen["pred"]):
                raise ValueError(f"fallback id {record_id} also repeats")
        selected.append(
            {
                "id": record_id,
                "pred": chosen["pred"],
                "primary_text": qwen_record["pred"],
                "external_text": dots[record_id]["pred"],
                "input_sha256": qwen_record["input_sha256"],
                "selected_engine": "dots.mocr" if use_fallback else "qwen3.5-ocr-jp-2b",
                "selection_reason": reasons.get(record_id, "qwen_clean"),
                "selected_model_revision": chosen["model_revision"],
                "selected_model_fingerprint": chosen["model_fingerprint"],
                "selected_prompt_id": chosen["prompt_id"],
                "qwen_model_revision": qwen_record["model_revision"],
                "qwen_model_fingerprint": qwen_record["model_fingerprint"],
                "dots_model_revision": dots[record_id]["model_revision"],
                "dots_model_fingerprint": dots[record_id]["model_fingerprint"],
            }
        )
    return selected


def _write_atomic(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qwen-predictions", type=Path, required=True)
    parser.add_argument("--dots-predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selected = select_predictions(
        qwen_path=args.qwen_predictions,
        dots_path=args.dots_predictions,
    )
    _write_atomic(args.output, selected)
    fallback_count = sum(record["selected_engine"] == "dots.mocr" for record in selected)
    print(f"selected {len(selected)} pages: qwen={len(selected) - fallback_count}, dots.mocr={fallback_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
