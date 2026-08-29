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
_NOVEL_DB_SERVICE_DIR = _BACKEND_DIR / "services" / "novel_db"
for _import_path in (_NOVEL_DB_SERVICE_DIR, _MAINTENANCE_DIR):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

from ocr_candidate_selection import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    is_external_materially_more_complete,
)
from ocr_content_guards import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    has_suspicious_repetition,
)
from qwen35_ocr_jp_vertical_predict import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    fallback_markup_tags,
    has_suspicious_vertical_bbox_order,
)


def _load_predictions(
    path: Path,
    *,
    source: str,
    allow_empty_candidates: bool = False,
) -> dict[str, dict[str, Any]]:
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
                raise ValueError(
                    f"{source} line {line_number} is invalid JSON: {exc.msg}"
                ) from exc
            if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                raise ValueError(f"{source} line {line_number} has no string id")
            record_id = record["id"]
            if record_id in records:
                raise ValueError(f"{source} contains duplicate id: {record_id}")
            if not isinstance(record.get("pred"), str):
                raise ValueError(f"{source} id {record_id} has an empty prediction")
            if not record["pred"].strip() and not (
                allow_empty_candidates
                and (
                    isinstance(record.get("candidate_error"), str)
                    or record.get("image_only") is True
                )
            ):
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


def _provenance_signature(
    record: Mapping[str, Any], *, source: str
) -> tuple[str, str, str]:
    _require_provenance(record, source=source)
    return (
        str(record["model_revision"]),
        str(record["model_fingerprint"]),
        str(record["prompt_id"]),
    )


def _provenance(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: record.get(field)
        for field in (
            "model_revision",
            "model_fingerprint",
            "engine_version",
            "prompt_id",
            "prompt_sha256",
            "seed",
            "max_tokens",
            "temperature",
            "top_p",
            "response_mode",
            "generated_at",
            "elapsed_seconds",
            "candidate_error",
            "image_only",
            "html_truncated",
            "suspicious_repetition",
            "fallback_markup_tags",
            "suspicious_vertical_bbox_order",
        )
    }


def _validate_prediction_scope(
    qwen: Mapping[str, Mapping[str, Any]],
    dots: Mapping[str, Mapping[str, Any]],
) -> None:
    missing = sorted(set(qwen) - set(dots))
    extra = sorted(set(dots) - set(qwen))
    if missing:
        raise ValueError(f"dots predictions are missing qwen ids: {missing[:20]}")
    if extra:
        raise ValueError(f"dots predictions contain non-qwen ids: {extra[:20]}")
    qwen_signatures = {
        _provenance_signature(record, source="qwen") for record in qwen.values()
    }
    dots_signatures = {
        _provenance_signature(record, source="dots") for record in dots.values()
    }
    if len(qwen_signatures) != 1:
        raise ValueError("qwen predictions mix model or prompt provenance")
    if len(dots_signatures) != 1:
        raise ValueError("dots predictions mix model or prompt provenance")


def _validated_qwen_signals(
    record_id: str,
    record: Mapping[str, Any],
) -> tuple[bool, tuple[str, ...], bool]:
    if not isinstance(record.get("html_truncated"), bool):
        raise ValueError(f"qwen id {record_id} has no html_truncated flag")
    if not isinstance(record.get("suspicious_repetition"), bool):
        raise ValueError(f"qwen id {record_id} has no suspicious_repetition flag")
    prediction = str(record["pred"])
    repetition = has_suspicious_repetition(prediction)
    if record["suspicious_repetition"] != repetition:
        raise ValueError(f"qwen id {record_id} repetition flag mismatch")
    raw_response = record.get("raw_response")
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise ValueError(f"qwen id {record_id} has no raw_response")
    markup_tags = fallback_markup_tags(raw_response)
    stored_tags = record.get("fallback_markup_tags")
    if stored_tags is not None and stored_tags != list(markup_tags):
        raise ValueError(f"qwen id {record_id} fallback markup mismatch")
    bbox_order_suspicious = has_suspicious_vertical_bbox_order(raw_response)
    stored_bbox_order = record.get("suspicious_vertical_bbox_order")
    if stored_bbox_order is not None and stored_bbox_order != bbox_order_suspicious:
        raise ValueError(f"qwen id {record_id} bbox order flag mismatch")
    return repetition, markup_tags, bbox_order_suspicious


def _qwen_flags(record_id: str, record: Mapping[str, Any]) -> list[str]:
    repetition, markup_tags, bbox_order_suspicious = _validated_qwen_signals(
        record_id, record
    )
    flags = []
    if isinstance(record.get("candidate_error"), str):
        flags.append("qwen_candidate_error")
    if repetition:
        flags.append("suspicious_repetition")
    if record["html_truncated"]:
        flags.append("html_truncated")
    if markup_tags:
        flags.append(f"unsupported_markup:{','.join(markup_tags)}")
    if bbox_order_suspicious:
        flags.append("suspicious_vertical_bbox_order")
    return flags


def _validate_image_only(record_id: str, dots_record: Mapping[str, Any]) -> None:
    try:
        dots_cells = json.loads(str(dots_record.get("raw_response") or ""))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"dots id {record_id} image-only raw response is invalid"
        ) from exc
    safe = (
        isinstance(dots_cells, list)
        and bool(dots_cells)
        and all(
            isinstance(cell, dict)
            and cell.get("category") == "Picture"
            and not (isinstance(cell.get("text"), str) and cell["text"].strip())
            for cell in dots_cells
        )
    )
    if not safe:
        raise ValueError(f"dots id {record_id} has an unsafe empty prediction")


def _selection_decision(
    record_id: str,
    qwen_record: Mapping[str, Any],
    dots_record: Mapping[str, Any],
) -> tuple[bool, str]:
    if dots_record["input_sha256"] != qwen_record["input_sha256"]:
        raise ValueError(f"dots id {record_id} input_sha256 mismatch")
    flags = _qwen_flags(record_id, qwen_record)
    qwen_text = str(qwen_record["pred"])
    dots_text = str(dots_record["pred"])
    if isinstance(dots_record.get("candidate_error"), str):
        reason = (
            "qwen_flagged_dots_candidate_error"
            if flags
            else "qwen_clean_dots_candidate_error"
        )
        return False, reason
    if (
        not qwen_text.strip()
        and not dots_text.strip()
        and dots_record.get("image_only") is True
    ):
        _validate_image_only(record_id, dots_record)
        return True, "dots_image_only_review_required"
    if flags and dots_text.strip():
        return True, "+".join(flags)
    if flags:
        return False, "qwen_flagged_dots_empty_review_required"
    if not has_suspicious_repetition(
        dots_text
    ) and is_external_materially_more_complete(qwen_text, dots_text):
        return True, "dots_materially_more_complete"
    return False, "qwen_clean"


def _selected_record(
    record_id: str,
    qwen_record: Mapping[str, Any],
    dots_record: Mapping[str, Any],
    *,
    use_fallback: bool,
    reason: str,
) -> dict[str, Any]:
    chosen = dots_record if use_fallback else qwen_record
    if (
        use_fallback
        and str(chosen["pred"]).strip()
        and has_suspicious_repetition(str(chosen["pred"]))
    ):
        raise ValueError(f"fallback id {record_id} also repeats")
    return {
        "id": record_id,
        "pred": chosen["pred"],
        "primary_text": qwen_record["pred"],
        "external_text": dots_record["pred"],
        "primary_raw_output": qwen_record["raw_response"],
        "external_raw_output": dots_record.get("raw_response", ""),
        "primary_provenance": _provenance(qwen_record),
        "external_provenance": _provenance(dots_record),
        "input_sha256": qwen_record["input_sha256"],
        "selected_engine": "dots.mocr" if use_fallback else "qwen3.5-ocr-jp-2b",
        "selection_reason": reason,
        "selected_model_revision": chosen["model_revision"],
        "selected_model_fingerprint": chosen["model_fingerprint"],
        "selected_prompt_id": chosen["prompt_id"],
        "qwen_model_revision": qwen_record["model_revision"],
        "qwen_model_fingerprint": qwen_record["model_fingerprint"],
        "dots_model_revision": dots_record["model_revision"],
        "dots_model_fingerprint": dots_record["model_fingerprint"],
    }


def select_predictions(
    *,
    qwen_path: Path,
    dots_path: Path,
    allow_empty_candidates: bool = False,
) -> list[dict[str, Any]]:
    qwen = _load_predictions(
        qwen_path,
        source="qwen",
        allow_empty_candidates=allow_empty_candidates,
    )
    if not qwen:
        raise ValueError("qwen prediction scope is empty")
    dots = _load_predictions(
        dots_path,
        source="dots",
        allow_empty_candidates=allow_empty_candidates,
    )
    _validate_prediction_scope(qwen, dots)
    selected: list[dict[str, Any]] = []
    for record_id, qwen_record in qwen.items():
        dots_record = dots[record_id]
        use_fallback, reason = _selection_decision(record_id, qwen_record, dots_record)
        selected.append(
            _selected_record(
                record_id,
                qwen_record,
                dots_record,
                use_fallback=use_fallback,
                reason=reason,
            )
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
                stream.write(
                    json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                )
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
    parser.add_argument("--allow-empty-candidates", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selected = select_predictions(
        qwen_path=args.qwen_predictions,
        dots_path=args.dots_predictions,
        allow_empty_candidates=args.allow_empty_candidates,
    )
    _write_atomic(args.output, selected)
    fallback_count = sum(
        record["selected_engine"] == "dots.mocr" for record in selected
    )
    print(
        f"selected {len(selected)} pages: qwen={len(selected) - fallback_count}, dots.mocr={fallback_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
