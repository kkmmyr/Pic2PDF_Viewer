"""Evaluate public vertical-Japanese OCR predictions without running a model.

The input contract follows llm-jp/eval_vertical_ja: metadata and predictions are
JSON Lines files keyed by ``id``; predictions store generated text in ``pred``.
This command intentionally does not remove repeated output because repetition is
an OCR failure mode in the B-35 screening stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MAINTENANCE_DIR = Path(__file__).resolve().parent
if str(_MAINTENANCE_DIR) in sys.path:
    sys.path.remove(str(_MAINTENANCE_DIR))
sys.path.insert(0, str(_MAINTENANCE_DIR))

from ocr_benchmark_text import (  # pyright: ignore[reportImplicitRelativeImport]  # noqa: E402
    NORMALIZATION_VERSION,
    _normalize_text,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def edit_distance(reference: str, hypothesis: str) -> int:
    """Return Levenshtein distance using a Unicode-safe Myers bit vector."""
    if not reference:
        return len(hypothesis)
    if not hypothesis:
        return len(reference)

    pattern_masks: dict[str, int] = defaultdict(int)
    for index, character in enumerate(reference):
        pattern_masks[character] |= 1 << index

    pattern_bits = (1 << len(reference)) - 1
    highest_bit = 1 << (len(reference) - 1)
    positive = pattern_bits
    negative = 0
    distance = len(reference)
    for character in hypothesis:
        equal = pattern_masks[character]
        vertical = equal | negative
        horizontal = (((equal & positive) + positive) ^ positive) | equal
        positive_horizontal = negative | ~(horizontal | positive)
        negative_horizontal = positive & horizontal
        if positive_horizontal & highest_bit:
            distance += 1
        elif negative_horizontal & highest_bit:
            distance -= 1
        positive_horizontal = (positive_horizontal << 1) | 1
        negative_horizontal <<= 1
        positive = negative_horizontal | ~(vertical | positive_horizontal)
        negative = positive_horizontal & vertical
        positive &= pattern_bits
        negative &= pattern_bits
    return distance


def _canonical_id(value: Any, *, source: str, line_number: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{source} line {line_number} has invalid id: {value!r}")
    return str(value)


def load_jsonl(path: Path, *, source: str) -> dict[str, dict[str, Any]]:
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
            if not isinstance(record, dict) or "id" not in record:
                raise ValueError(
                    f"{source} line {line_number} must be an object with id"
                )
            record_id = _canonical_id(
                record["id"], source=source, line_number=line_number
            )
            if record_id in records:
                raise ValueError(f"{source} contains duplicate id: {record_id}")
            records[record_id] = record
    if not records:
        raise ValueError(f"{source} is empty")
    return records


def _selected_metadata(
    metadata: dict[str, dict[str, Any]], dataset: str, include_horizontal: bool
) -> dict[str, dict[str, Any]]:
    if dataset == "vjroda" or include_horizontal:
        return metadata
    selected: dict[str, dict[str, Any]] = {}
    for record_id, record in metadata.items():
        is_vertical = record.get("is_vertical")
        if not isinstance(is_vertical, bool):
            raise ValueError(
                f"JSSODa metadata id {record_id} has non-boolean is_vertical"
            )
        if is_vertical:
            selected[record_id] = record
    if not selected:
        raise ValueError("JSSODa vertical scope is empty")
    return selected


def _validate_coverage(
    metadata: dict[str, dict[str, Any]], predictions: dict[str, dict[str, Any]]
) -> None:
    metadata_ids = set(metadata)
    prediction_ids = set(predictions)
    missing = sorted(metadata_ids - prediction_ids)
    extra = sorted(prediction_ids - metadata_ids)
    if missing or extra:
        raise ValueError(
            "prediction ID coverage mismatch: "
            f"missing={missing[:20]}, extra={extra[:20]}"
        )


def _reference_text(record: dict[str, Any], dataset: str, record_id: str) -> str:
    field = "passage" if dataset == "jssoda" else "text"
    value = record.get(field)
    if not isinstance(value, str):
        raise ValueError(f"{dataset} metadata id {record_id} has no string {field}")
    if dataset == "vjroda":
        for tag in ("header", "footer", "caption"):
            value = value.replace(f"<{tag}>", "").replace(f"</{tag}>", "")
    return value


def _metric_groups(record: dict[str, Any], dataset: str) -> tuple[str, ...]:
    if dataset == "vjroda":
        return ("overall", "dataset:vjroda")
    is_vertical = record.get("is_vertical")
    num_columns = record.get("num_columns")
    if not isinstance(is_vertical, bool):
        raise ValueError("JSSODa is_vertical must be boolean")
    if isinstance(num_columns, bool) or not isinstance(num_columns, int):
        raise ValueError("JSSODa num_columns must be an integer")
    direction = "vertical" if is_vertical else "horizontal"
    return ("overall", f"direction:{direction}", f"{direction}:columns:{num_columns}")


def build_report(
    *,
    dataset: str,
    metadata_path: Path,
    prediction_path: Path,
    engine_label: str,
    model_revision: str,
    prompt_id: str,
    seed: str,
    include_horizontal: bool = False,
) -> dict[str, Any]:
    metadata_all = load_jsonl(metadata_path, source="metadata")
    metadata = _selected_metadata(metadata_all, dataset, include_horizontal)
    predictions = load_jsonl(prediction_path, source="predictions")
    _validate_coverage(metadata, predictions)

    totals: dict[str, dict[str, int | float]] = defaultdict(
        lambda: {
            "page_count": 0,
            "exact_match_count": 0,
            "total_edit_distance": 0,
            "total_reference_chars": 0,
            "max_page_cer": 0.0,
        }
    )
    pages: list[dict[str, Any]] = []
    for record_id, record in metadata.items():
        prediction = predictions[record_id].get("pred")
        if not isinstance(prediction, str):
            raise ValueError(f"prediction id {record_id} has no string pred")
        reference = _reference_text(record, dataset, record_id)
        normalized_reference = _normalize_text(reference)
        normalized_prediction = _normalize_text(prediction)
        if not normalized_reference:
            raise ValueError(f"metadata id {record_id} has empty normalized reference")
        distance = edit_distance(normalized_reference, normalized_prediction)
        reference_chars = len(normalized_reference)
        page_cer = distance / reference_chars
        exact_match = normalized_reference == normalized_prediction
        groups = _metric_groups(record, dataset)
        for group in groups:
            total = totals[group]
            total["page_count"] = int(total["page_count"]) + 1
            total["exact_match_count"] = int(total["exact_match_count"]) + int(
                exact_match
            )
            total["total_edit_distance"] = int(total["total_edit_distance"]) + distance
            total["total_reference_chars"] = (
                int(total["total_reference_chars"]) + reference_chars
            )
            total["max_page_cer"] = max(float(total["max_page_cer"]), page_cer)
        page = {
            "id": record["id"],
            "reference_chars": reference_chars,
            "hypothesis_chars": len(normalized_prediction),
            "edit_distance": distance,
            "cer": page_cer,
            "exact_match": exact_match,
        }
        if dataset == "jssoda":
            page["is_vertical"] = record["is_vertical"]
            page["num_columns"] = record["num_columns"]
        pages.append(page)

    metrics = []
    for group in sorted(totals, key=lambda value: (value != "overall", value)):
        total = totals[group]
        page_count = int(total["page_count"])
        reference_chars = int(total["total_reference_chars"])
        metrics.append(
            {
                "group": group,
                **total,
                "aggregate_cer": int(total["total_edit_distance"]) / reference_chars,
                "exact_match_rate": int(total["exact_match_count"]) / page_count,
            }
        )

    return {
        "schema_version": 1,
        "purpose": "public_vertical_japanese_screening_not_formal_holdout",
        "dataset": dataset,
        "scope": "all" if dataset == "vjroda" or include_horizontal else "vertical",
        "engine": engine_label,
        "model_revision": model_revision,
        "prompt_id": prompt_id,
        "seed": seed,
        "normalization_version": NORMALIZATION_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "inputs": {
            "metadata_sha256": _sha256(metadata_path),
            "predictions_sha256": _sha256(prediction_path),
        },
        "metrics": metrics,
        "pages": pages,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=("jssoda", "vjroda"), required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine-label", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--prompt-id", required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--include-horizontal", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(
        dataset=args.dataset,
        metadata_path=args.metadata,
        prediction_path=args.predictions,
        engine_label=args.engine_label,
        model_revision=args.model_revision,
        prompt_id=args.prompt_id,
        seed=args.seed,
        include_horizontal=args.include_horizontal,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for metric in report["metrics"]:
        print(
            f"{metric['group']}: pages={metric['page_count']}, "
            f"CER={float(metric['aggregate_cer']) * 100:.4f}%, "
            f"max={float(metric['max_page_cer']) * 100:.4f}%, "
            f"exact={float(metric['exact_match_rate']) * 100:.2f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
