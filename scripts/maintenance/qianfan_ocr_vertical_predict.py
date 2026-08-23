"""Generate resumable Qianfan-OCR predictions for JSSODa vertical pages.

The runner reuses the audited MLX checkpoint and metadata contracts from the
dots.mocr screening CLI. Qianfan output is preserved verbatim so Markdown,
extra explanation, and generation repetition remain observable gate failures.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

if __package__:
    from .dots_mocr_vertical_predict import RunConfig, _MlxVlmEngine, run_predictions
else:
    from dots_mocr_vertical_predict import (  # type: ignore[import-not-found]
        RunConfig,
        _MlxVlmEngine,
        run_predictions,
    )

OCR_PROMPT = "Parse this document to Markdown."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--engine-version", default="0.6.15")
    parser.add_argument("--prompt-id", default="qianfan-ocr-markdown-v1")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--id", action="append", dest="selected_ids", default=[])
    parser.add_argument("--allow-custom-model-code", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit is not None and args.selected_ids:
        raise ValueError("--limit and --id are mutually exclusive")
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")
    if args.max_tokens <= 0:
        raise ValueError("--max-tokens must be positive")
    if args.temperature < 0:
        raise ValueError("--temperature must be non-negative")
    if not 0 < args.top_p <= 1:
        raise ValueError("--top-p must be in (0, 1]")
    config = RunConfig(
        metadata_path=args.metadata,
        dataset_root=args.dataset_root,
        output_path=args.output,
        model_path=args.model_path,
        model_revision=args.model_revision,
        engine_version=args.engine_version,
        prompt_id=args.prompt_id,
        prompt=OCR_PROMPT,
        seed=args.seed,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        limit=args.limit,
        selected_ids=tuple(args.selected_ids),
        response_mode="plain_text",
        allow_custom_model_code=args.allow_custom_model_code,
    )
    generated, completed = run_predictions(config, engine_factory=_MlxVlmEngine)
    print(f"run complete: generated={generated}, checkpoint_total={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
