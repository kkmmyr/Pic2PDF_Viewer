"""Generate resumable Unlimited-OCR predictions for JSSODa vertical pages."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

_MAINTENANCE_DIR = Path(__file__).resolve().parent
if str(_MAINTENANCE_DIR) not in sys.path:
    sys.path.insert(0, str(_MAINTENANCE_DIR))

from dots_mocr_vertical_predict import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    RunConfig,
    _append_checkpoint,
    _load_checkpoint,
    _sha256,
    _validate_checkpoint,
    load_vertical_pages,
)

MODEL_REVISION = "6d9f675e3fa73dd49cd03f630868b1941c72803f"
PROMPT_ID = "unlimited-ocr-document-parsing-v1"
PROMPT = "document parsing."
MODEL_FILES = frozenset(
    {
        "chat_template.jinja",
        "config.json",
        "configuration_deepseek_v2.py",
        "conversation.py",
        "deepencoder.py",
        "model.safetensors.index.json",
        "modeling_deepseekv2.py",
        "modeling_unlimitedocr.py",
        "processor_config.json",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
    }
)


class PredictionEngine(Protocol):
    def generate(self, image_path: Path) -> str: ...


def model_fingerprint(model_path: Path) -> str:
    root = model_path.resolve()
    if not root.is_dir():
        raise ValueError(f"model path is not a directory: {root}")
    missing = sorted(name for name in MODEL_FILES if not (root / name).is_file())
    if missing:
        raise ValueError(f"model snapshot is missing required files: {missing}")
    weights = sorted(root.glob("*.safetensors"))
    if not weights:
        raise ValueError("model snapshot has no safetensors weights")
    files = sorted(root / name for name in MODEL_FILES) + weights
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(_sha256(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def run_predictions(
    config: RunConfig,
    *,
    engine_factory: Callable[[RunConfig], PredictionEngine],
) -> tuple[int, int]:
    pages = load_vertical_pages(config)
    fingerprint = model_fingerprint(config.model_path)
    checkpoint = _load_checkpoint(config.output_path)
    _validate_checkpoint(
        config=config,
        pages=pages,
        checkpoint=checkpoint,
        fingerprint=fingerprint,
    )
    pending = [page for page in pages if page.record_id not in checkpoint]
    if not pending:
        print(f"complete: {len(pages)}/{len(pages)} pages already checkpointed")
        return 0, len(pages)

    engine = engine_factory(config)
    prompt_sha256 = hashlib.sha256(config.prompt.encode()).hexdigest()
    completed = len(checkpoint)
    for page in pending:
        started_at = time.monotonic()
        prediction = engine.generate(page.image_path)
        elapsed = time.monotonic() - started_at
        if not isinstance(prediction, str) or not prediction.strip():
            raise ValueError(f"Unlimited-OCR prediction id {page.record_id} is empty")
        _append_checkpoint(
            config.output_path,
            {
                "id": page.record_id,
                "pred": prediction,
                "input_sha256": page.image_sha256,
                "image_relpath": page.image_relpath,
                "model_revision": config.model_revision,
                "model_fingerprint": fingerprint,
                "engine_version": config.engine_version,
                "prompt_id": config.prompt_id,
                "prompt_sha256": prompt_sha256,
                "seed": config.seed,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
                "top_p": config.top_p,
                "response_mode": config.response_mode,
                "elapsed_seconds": elapsed,
                "generated_at": datetime.now(UTC).isoformat(),
            },
        )
        completed += 1
        print(
            f"checkpointed {page.record_id}: {completed}/{len(pages)} "
            f"(elapsed={elapsed:.2f}s, chars={len(prediction)})",
            flush=True,
        )
    return len(pending), completed


class _MlxVlmEngine:
    def __init__(self, config: RunConfig) -> None:
        installed = importlib.metadata.version("mlx-vlm")
        if installed != config.engine_version:
            raise ValueError(
                f"mlx-vlm version mismatch: {installed} != {config.engine_version}"
            )
        from mlx_vlm import generate, load  # pyright: ignore[reportMissingImports]
        from mlx_vlm.prompt_utils import (  # pyright: ignore[reportMissingImports]
            apply_chat_template,
        )

        self._generate = generate
        self._config = config
        self._model, self._processor = load(config.model_path.as_posix(), lazy=False)
        self._formatted_prompt = apply_chat_template(
            self._processor,
            self._model.config,
            config.prompt,
            num_images=1,
        )

    def generate(self, image_path: Path) -> str:
        result = self._generate(
            self._model,
            self._processor,
            self._formatted_prompt,
            image=image_path.as_posix(),
            verbose=False,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
            top_p=self._config.top_p,
            seed=self._config.seed,
            skip_special_tokens=True,
            cropping=True,
            base_size=1024,
            image_size=640,
        )
        text = getattr(result, "text", None)
        if not isinstance(text, str):
            raise ValueError("MLX-VLM generation result has no string text")
        return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-revision", default=MODEL_REVISION)
    parser.add_argument("--engine-version", default="0.6.15")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--id", action="append", dest="selected_ids", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.model_revision != MODEL_REVISION:
        raise ValueError(f"unsupported model revision: {args.model_revision}")
    if args.limit is not None and args.selected_ids:
        raise ValueError("--limit and --id are mutually exclusive")
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")
    if args.max_tokens <= 0:
        raise ValueError("--max-tokens must be positive")
    config = RunConfig(
        metadata_path=args.metadata,
        dataset_root=args.dataset_root,
        output_path=args.output,
        model_path=args.model_path,
        model_revision=args.model_revision,
        engine_version=args.engine_version,
        prompt_id=PROMPT_ID,
        prompt=PROMPT,
        seed=args.seed,
        max_tokens=args.max_tokens,
        temperature=0.0,
        top_p=1.0,
        limit=args.limit,
        selected_ids=tuple(args.selected_ids),
        response_mode="plain_text",
    )
    generated, completed = run_predictions(config, engine_factory=_MlxVlmEngine)
    print(f"run complete: generated={generated}, checkpoint_total={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
