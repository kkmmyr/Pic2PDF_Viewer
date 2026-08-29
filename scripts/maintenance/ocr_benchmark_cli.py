"""Command-line orchestration for the OCR ground-truth benchmark."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import ocr_benchmark_columns as column_engines
import ocr_benchmark_engines as engines
from ocr_benchmark_gate import evaluate_quality_gate
from ocr_holdout_ledger import retire_formal_holdout_to_tuning
from ocr_holdout_manifest import authorize_formal_holdout_open, build_formal_gate_policy
from ocr_benchmark_report import (
    _print_summary,
    filter_entries,
    summarize,
)

DEFAULT_POLICY_PATH = Path(__file__).with_name("ocr_quality_policy.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "engine",
        choices=(
            "current",
            "qa-primary",
            "qa-external",
            "tesseract",
            "yomitoku",
            "ndlocr",
            "paddle",
            "paddle-columns",
            "surya-columns",
            "report",
        ),
    )
    parser.add_argument("--api-base", default="http://medaroserver:8090")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tesseract", type=Path)
    parser.add_argument("--tessdata-dir", type=Path)
    parser.add_argument("--ocr-python", type=Path)
    parser.add_argument("--ocr-path", type=Path)
    parser.add_argument(
        "--yomitoku-device",
        choices=("auto", "cuda", "mps", "cpu"),
        default="auto",
        help="yomitoku device passed to the external OCR wrapper",
    )
    parser.add_argument("--ndlocr-python", type=Path)
    parser.add_argument("--ndlocr-script", type=Path)
    parser.add_argument("--ndlocr-rec-weights", type=Path)
    parser.add_argument("--paddle-python", type=Path)
    parser.add_argument(
        "--paddle-worker",
        type=Path,
        default=Path(__file__).with_name("paddle_ocr_worker.py"),
    )
    parser.add_argument("--paddle-device", default="cpu")
    parser.add_argument("--paddle-det-limit-side-len", type=int, default=960)
    parser.add_argument(
        "--paddle-column-worker",
        type=Path,
        default=Path(__file__).with_name("paddle_column_ocr_worker.py"),
    )
    parser.add_argument("--segment-report", type=Path)
    parser.add_argument("--paddle-column-margin", type=int, default=8)
    parser.add_argument("--paddle-column-scale", type=float, default=2.0)
    parser.add_argument(
        "--surya-column-worker",
        type=Path,
        default=Path(__file__).with_name("surya_column_ocr_worker.py"),
    )
    parser.add_argument("--surya-server", type=Path)
    parser.add_argument("--surya-model-path", type=Path)
    parser.add_argument("--surya-mmproj-path", type=Path)
    parser.add_argument("--surya-group-size", type=int, default=4)
    parser.add_argument("--surya-column-margin", type=int, default=12)
    parser.add_argument("--engine-label")
    parser.add_argument("--source-report", type=Path)
    parser.add_argument("--corpus-json", type=Path)
    parser.add_argument("--entry-id", type=int, action="append")
    parser.add_argument("--run-id", type=int, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--fail-on-gate", action="store_true")
    parser.add_argument("--formal-holdout-manifest", type=Path)
    parser.add_argument("--holdout-package-root", type=Path)
    parser.add_argument("--holdout-ledger", type=Path)
    parser.add_argument("--holdout-operator")
    parser.add_argument("--holdout-reason")
    return parser


def _load_corpus(args: argparse.Namespace) -> dict[str, Any]:
    if args.corpus_json is not None:
        return json.loads(args.corpus_json.read_text(encoding="utf-8"))
    return engines._get_json(f"{args.api_base.rstrip('/')}/api/ocr/ground-truth")


def _require(
    parser: argparse.ArgumentParser,
    condition: bool,
    message: str,
) -> None:
    if not condition:
        parser.error(message)


def _run_local_engine(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    entries: list[dict[str, Any]],
) -> tuple[dict[int, str], dict[int, list[dict[str, Any]]] | None] | None:
    if args.engine == "current":
        return {int(entry["id"]): str(entry["ocr_text"]) for entry in entries}, None
    if args.engine in {"qa-primary", "qa-external"}:
        field = "primary_text" if args.engine == "qa-primary" else "external_text"
        return engines._run_qa_candidate(entries, args.api_base, field), None
    if args.engine == "report":
        _require(
            parser, args.source_report is not None, "report requires --source-report"
        )
        return engines._load_hypotheses_from_report(entries, args.source_report), None
    return None


def _run_downloaded_engine(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    entries: list[dict[str, Any]],
    image_paths: dict[int, Path],
    repo_root: Path,
    work_dir: Path,
) -> tuple[dict[int, str], dict[int, list[dict[str, Any]]] | None]:
    if args.engine == "tesseract":
        _require(
            parser,
            args.tesseract is not None and args.tessdata_dir is not None,
            "tesseract requires --tesseract and --tessdata-dir",
        )
        return (
            engines._run_tesseract(
                entries, image_paths, args.tesseract, args.tessdata_dir
            ),
            None,
        )
    if args.engine == "yomitoku":
        _require(
            parser,
            args.ocr_python is not None and args.ocr_path is not None,
            "yomitoku requires --ocr-python and --ocr-path",
        )
        return (
            engines._run_yomitoku(
                entries,
                image_paths,
                args.ocr_python,
                args.ocr_path,
                repo_root,
                work_dir,
                args.yomitoku_device,
            ),
            None,
        )
    if args.engine == "ndlocr":
        _require(
            parser,
            args.ndlocr_python is not None and args.ndlocr_script is not None,
            "ndlocr requires --ndlocr-python and --ndlocr-script",
        )
        if args.ndlocr_rec_weights is not None:
            _require(
                parser,
                args.ndlocr_rec_weights.is_file(),
                "--ndlocr-rec-weights must be an existing file",
            )
            args.ndlocr_rec_weights = args.ndlocr_rec_weights.resolve()
        return engines._run_ndlocr(
            entries,
            image_paths,
            args.ndlocr_python,
            args.ndlocr_script,
            work_dir,
            args.ndlocr_rec_weights,
        )
    if args.engine == "paddle":
        _require(
            parser, args.paddle_python is not None, "paddle requires --paddle-python"
        )
        return column_engines._run_paddle(
            entries,
            image_paths,
            args.paddle_python,
            args.paddle_worker,
            args.paddle_device,
            args.paddle_det_limit_side_len,
            work_dir,
        )
    if args.engine == "paddle-columns":
        _require(
            parser,
            args.paddle_python is not None and args.segment_report is not None,
            "paddle-columns requires --paddle-python and --segment-report",
        )
        return column_engines._run_paddle_columns(
            entries,
            image_paths,
            args.segment_report,
            args.paddle_python,
            args.paddle_column_worker,
            args.paddle_device,
            args.paddle_column_margin,
            args.paddle_column_scale,
            work_dir,
        )
    _require(
        parser,
        all(
            value is not None
            for value in (
                args.segment_report,
                args.surya_server,
                args.surya_model_path,
                args.surya_mmproj_path,
            )
        ),
        "surya-columns requires --segment-report, --surya-server, "
        "--surya-model-path, and --surya-mmproj-path",
    )
    return column_engines._run_surya_columns(
        entries,
        image_paths,
        args.segment_report,
        args.surya_column_worker,
        args.surya_server,
        args.surya_model_path,
        args.surya_mmproj_path,
        args.surya_group_size,
        args.surya_column_margin,
        work_dir,
    )


def _collect_hypotheses(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    entries: list[dict[str, Any]],
    repo_root: Path,
    work_dir: Path,
) -> tuple[dict[int, str], dict[int, list[dict[str, Any]]] | None]:
    local_result = _run_local_engine(args, parser, entries)
    if local_result is not None:
        return local_result
    image_paths = engines._download_images(entries, args.api_base, work_dir)
    return _run_downloaded_engine(
        args, parser, entries, image_paths, repo_root, work_dir
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    corpus = _load_corpus(args)
    entries = filter_entries(
        [entry for entry in corpus["entries"] if entry["state"] == "verified"],
        entry_ids=set(args.entry_id) if args.entry_id else None,
        run_ids=set(args.run_id) if args.run_id else None,
    )
    if not entries:
        raise RuntimeError("verified ground-truth corpus is empty")

    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    gate_policy = policy
    formal_holdout = None
    if args.formal_holdout_manifest is not None:
        _require(
            parser,
            not args.entry_id and not args.run_id,
            "formal holdout cannot be combined with entry/run filters",
        )
        _require(
            parser,
            args.holdout_ledger is not None,
            "formal holdout requires --holdout-ledger",
        )
        _require(
            parser,
            bool(args.holdout_operator),
            "formal holdout requires --holdout-operator",
        )
        _require(
            parser,
            bool(args.holdout_reason),
            "formal holdout requires --holdout-reason",
        )
        manifest = json.loads(args.formal_holdout_manifest.read_text(encoding="utf-8"))
        manifest_ids = [int(item["entry_id"]) for item in manifest.get("entries", [])]
        entries = filter_entries(entries, entry_ids=set(manifest_ids), run_ids=None)
        if len(entries) != len(manifest_ids):
            raise ValueError("formal holdout manifest contains duplicate entry IDs")
        formal_holdout = authorize_formal_holdout_open(
            manifest,
            {**corpus, "entries": entries},
            policy,
            package_root=args.holdout_package_root
            or args.formal_holdout_manifest.parent,
            ledger_path=args.holdout_ledger,
            operator=args.holdout_operator,
            reason=args.holdout_reason,
        )
        gate_policy = build_formal_gate_policy(manifest, policy)

    repo_root = Path(__file__).resolve().parents[2]
    started_at = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="pic2pdf-ocr-benchmark-") as temp_dir:
        hypotheses, segments_by_entry = _collect_hypotheses(
            args, parser, entries, repo_root, Path(temp_dir)
        )

    report = summarize(
        entries,
        hypotheses,
        args.engine_label or args.engine,
        segments_by_entry,
    )
    report["engine_kind"] = args.engine
    report["elapsed_seconds"] = time.perf_counter() - started_at
    report["corpus_entry_ids"] = [int(entry["id"]) for entry in entries]
    report["quality_gate"] = evaluate_quality_gate(
        {**corpus, "entries": entries}, report, gate_policy
    )
    if formal_holdout is not None:
        report["formal_holdout"] = formal_holdout
    _print_summary(report)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if formal_holdout is not None and not report["quality_gate"]["passed"]:
        retire_formal_holdout_to_tuning(
            args.holdout_ledger,
            manifest,
            operator=args.holdout_operator,
            reason="one-time formal benchmark quality gate failed",
        )
    return 1 if args.fail_on_gate and not report["quality_gate"]["passed"] else 0
