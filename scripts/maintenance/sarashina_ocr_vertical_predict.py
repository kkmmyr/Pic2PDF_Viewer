"""Generate resumable Sarashina2.2-OCR predictions for JSSODa vertical pages."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
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

MODEL_REVISION = "eafb8d48cb2f2a3a6dce571d26b26586ff048fda"
IMAGE_ONLY_PROMPT_ID = "sarashina2.2-ocr-image-only-v1"
TRANSCRIPTION_PROMPT_ID = "sarashina2.2-ocr-transcription-ja-v1"
TRANSCRIPTION_PROMPT_JA = (
    "画像内の文章を読み順どおりに、そのまま文字起こししてください。"
    "要約、説明、箇条書き、Markdown、補足は出力せず、文字起こし本文だけを出力してください。"
)
CUSTOM_CODE_DIGESTS = {
    "configuration_sarashina2_vision.py": "31e9aa247d9c95e123763c57c7ddb844b844b4ea586e11135f64caddab7d1154",
    "modeling_sarashina2_vision.py": "2421b9343b93c9ccfffc352557ce9c92835239648278dc0735bc4315b691b331",
    "processing_sarashina2_vision.py": "e92e617957590210cef0abbcbe0a9248fdb56bbc46f4b0aa35a1d89274bf71e2",
}


class PredictionEngine(Protocol):
    def generate(self, image_path: Path) -> str: ...


def message_content(prompt_id: str, prompt: str, image: object) -> list[dict[str, object]]:
    content: list[dict[str, object]] = [{"type": "image", "image": image}]
    if prompt_id == IMAGE_ONLY_PROMPT_ID:
        return content
    if prompt_id == TRANSCRIPTION_PROMPT_ID:
        content.append({"type": "text", "text": prompt})
        return content
    raise ValueError(f"unsupported Sarashina prompt ID: {prompt_id}")


def model_fingerprint(model_path: Path) -> str:
    root = model_path.resolve()
    if not root.is_dir():
        raise ValueError(f"model path is not a directory: {root}")
    required = {
        "config.json",
        "generation_config.json",
        "preprocessor_config.json",
        "tokenizer.json",
        *CUSTOM_CODE_DIGESTS,
    }
    missing = sorted(name for name in required if not (root / name).is_file())
    if missing:
        raise ValueError(f"model snapshot is missing required files: {missing}")
    for name, expected in CUSTOM_CODE_DIGESTS.items():
        if _sha256(root / name) != expected:
            raise ValueError(f"audited custom model code digest mismatch: {name}")
    weights = sorted(root.glob("*.safetensors"))
    if not weights:
        raise ValueError("model snapshot has no safetensors weights")
    files = sorted(root / name for name in required) + weights
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
    repetition_penalty: float,
    engine_factory: Callable[[RunConfig, float], PredictionEngine],
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
    for record_id, record in checkpoint.items():
        if record.get("repetition_penalty") != repetition_penalty:
            raise ValueError(f"checkpoint id {record_id} repetition_penalty mismatch")
    pending = [page for page in pages if page.record_id not in checkpoint]
    if not pending:
        print(f"complete: {len(pages)}/{len(pages)} pages already checkpointed")
        return 0, len(pages)

    engine = engine_factory(config, repetition_penalty)
    prompt_sha256 = hashlib.sha256(config.prompt.encode()).hexdigest()
    completed = len(checkpoint)
    for page in pending:
        started_at = time.monotonic()
        prediction = engine.generate(page.image_path)
        elapsed = time.monotonic() - started_at
        if not isinstance(prediction, str) or not prediction.strip():
            raise ValueError(f"Sarashina2.2-OCR prediction id {page.record_id} is empty")
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
                "repetition_penalty": repetition_penalty,
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


class _MpsEngine:
    def __init__(self, config: RunConfig, repetition_penalty: float) -> None:
        if not config.allow_custom_model_code:
            raise ValueError(
                "Sarashina2.2-OCR requires audited custom model code; "
                "pass --allow-custom-model-code explicitly"
            )
        installed = importlib.metadata.version("transformers")
        if installed != config.engine_version:
            raise ValueError(
                f"transformers version mismatch: {installed} != {config.engine_version}"
            )
        import torch  # pyright: ignore[reportMissingImports]
        from transformers import (  # pyright: ignore[reportMissingImports]
            AutoModelForCausalLM,
            AutoProcessor,
        )

        if not torch.backends.mps.is_available():
            raise ValueError("PyTorch MPS is unavailable")
        self._torch = torch
        self._processor = AutoProcessor.from_pretrained(
            config.model_path,
            trust_remote_code=True,
            local_files_only=True,
            use_fast=False,
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            config.model_path,
            trust_remote_code=True,
            local_files_only=True,
            dtype=torch.bfloat16,
        ).to("mps").eval()
        self._config = config
        self._repetition_penalty = repetition_penalty

    def generate(self, image_path: Path) -> str:
        from PIL import Image
        from transformers import set_seed  # pyright: ignore[reportMissingImports]

        with Image.open(image_path) as source:
            image = source.convert("RGB")
        messages = [
            {
                "role": "user",
                "content": message_content(self._config.prompt_id, self._config.prompt, image),
            }
        ]
        inputs = self._processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to("mps")
        set_seed(self._config.seed)
        with self._torch.inference_mode():
            output = self._model.generate(
                **inputs,
                max_new_tokens=self._config.max_tokens,
                do_sample=False,
                repetition_penalty=self._repetition_penalty,
                use_cache=True,
            )
        generated = output[:, inputs["input_ids"].shape[1] :]
        return self._processor.batch_decode(
            generated, skip_special_tokens=True
        )[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-revision", default=MODEL_REVISION)
    parser.add_argument("--engine-version", default="4.57.1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--repetition-penalty", type=float, default=1.2)
    parser.add_argument("--prompt-mode", choices=("image-only", "transcription-ja"), default="image-only")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--id", action="append", dest="selected_ids", default=[])
    parser.add_argument("--allow-custom-model-code", action="store_true")
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
    if args.repetition_penalty <= 0:
        raise ValueError("--repetition-penalty must be positive")
    if args.prompt_mode == "image-only":
        prompt_id = IMAGE_ONLY_PROMPT_ID
        prompt_contract = json.dumps(
            {
                "chat": "single user image without text prompt",
                "repetition_penalty": args.repetition_penalty,
            },
            sort_keys=True,
        )
    else:
        prompt_id = TRANSCRIPTION_PROMPT_ID
        prompt_contract = TRANSCRIPTION_PROMPT_JA
    config = RunConfig(
        metadata_path=args.metadata,
        dataset_root=args.dataset_root,
        output_path=args.output,
        model_path=args.model_path,
        model_revision=args.model_revision,
        engine_version=args.engine_version,
        prompt_id=prompt_id,
        prompt=prompt_contract,
        seed=args.seed,
        max_tokens=args.max_tokens,
        temperature=0.0,
        top_p=0.95,
        limit=args.limit,
        selected_ids=tuple(args.selected_ids),
        response_mode="plain_text",
        allow_custom_model_code=args.allow_custom_model_code,
    )
    generated, completed = run_predictions(
        config,
        repetition_penalty=args.repetition_penalty,
        engine_factory=_MpsEngine,
    )
    print(f"run complete: generated={generated}, checkpoint_total={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
