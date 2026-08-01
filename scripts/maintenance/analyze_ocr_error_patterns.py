"""Classify verified OCR edit operations for B-35 diagnostics."""

from __future__ import annotations

import argparse
import importlib.util
import json
import unicodedata
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BENCHMARK_PATH = Path(__file__).with_name("benchmark_ocr_ground_truth.py")
_SPEC = importlib.util.spec_from_file_location("ocr_benchmark", _BENCHMARK_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"could not load OCR benchmark module: {_BENCHMARK_PATH}")
benchmark = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(benchmark)

_SMALL_KANA = frozenset("ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ")
_PUNCTUATION = frozenset(
    "、。・！？!?…‥「」『』（）()【】〈〉《》ー―—〜～：；:;,.\"'“”‘’"
)


def _char_category(char: str) -> str:
    if not char:
        return "empty"
    if char in _SMALL_KANA:
        return "small_kana"
    if char in _PUNCTUATION or unicodedata.category(char).startswith("P"):
        return "punctuation"
    codepoint = ord(char)
    if 0x4E00 <= codepoint <= 0x9FFF or 0x3400 <= codepoint <= 0x4DBF:
        return "kanji"
    if 0x3040 <= codepoint <= 0x30FF:
        return "kana"
    if char.isascii() and char.isalnum():
        return "ascii_or_digit"
    return "other"


def analyze(
    corpus: dict[str, Any], report: dict[str, Any], layout_type: str
) -> dict[str, Any]:
    entries = {
        int(entry["id"]): entry
        for entry in corpus["entries"]
        if entry["state"] == "verified"
    }
    operation_counts: Counter[str] = Counter()
    reference_category_counts: Counter[str] = Counter()
    confusion_counts: Counter[str] = Counter()
    pages = []
    for page in report["pages"]:
        if str(page.get("layout_type", "unknown")) != layout_type:
            continue
        entry_id = int(page["entry_id"])
        entry = entries.get(entry_id)
        if entry is None:
            raise ValueError(f"verified ground-truth entry missing: {entry_id}")
        if str(entry["image_sha256"]) != str(page["image_sha256"]):
            raise ValueError(f"image SHA-256 mismatch for entry {entry_id}")
        operations = benchmark.character_error_operations(
            str(entry["reference_text"]), str(page["hypothesis"])
        )
        for operation in operations:
            operation_name = str(operation["operation"])
            reference_char = str(operation["reference_char"])
            hypothesis_char = str(operation["hypothesis_char"])
            category = _char_category(reference_char or hypothesis_char)
            operation["category"] = category
            operation_counts[operation_name] += 1
            reference_category_counts[category] += 1
            confusion_counts[f"{reference_char}→{hypothesis_char}"] += 1
        pages.append(
            {
                "entry_id": entry_id,
                "run_id": int(page["run_id"]),
                "page_no": int(page["page_no"]),
                "operation_count": len(operations),
                "operations": operations,
            }
        )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": str(report["engine"]),
        "layout_type": layout_type,
        "page_count": len(pages),
        "total_operations": sum(operation_counts.values()),
        "operation_counts": dict(operation_counts),
        "category_counts": dict(reference_category_counts),
        "top_confusions": [
            {"pair": pair, "count": count}
            for pair, count in confusion_counts.most_common(30)
        ],
        "pages": pages,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--corpus-json", type=Path)
    parser.add_argument("--layout-type", default="normal_prose")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    corpus = (
        json.loads(args.corpus_json.read_text(encoding="utf-8"))
        if args.corpus_json is not None
        else benchmark._get_json(f"{args.api_base.rstrip('/')}/api/ocr/ground-truth")
    )
    report = json.loads(args.report.read_text(encoding="utf-8"))
    result = analyze(corpus, report, args.layout_type)
    print(f"engine: {result['engine']}")
    print(f"layout: {result['layout_type']}, pages: {result['page_count']}")
    print(f"operations: {result['operation_counts']}")
    print(f"categories: {result['category_counts']}")
    print(f"top_confusions: {result['top_confusions'][:10]}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
