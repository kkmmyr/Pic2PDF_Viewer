"""Generate resumable Qwen3.5-OCR-JP-2B predictions for JSSODa pages.

The model's fixed HTML prompt and greedy generation contract are preserved.
Each successful page checkpoints the raw HTML and its DOM-order visible text
before the next page starts. Ruby ``rt`` text is excluded from the prediction;
layout blocks are not reordered and repeated output is not repaired.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import re
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol

_ROOT_DIR = Path(__file__).resolve().parents[2]
_MAINTENANCE_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _ROOT_DIR / "backend"
_NOVEL_DB_SERVICE_DIR = _BACKEND_DIR / "services" / "novel_db"
for _import_path in (_MAINTENANCE_DIR, _NOVEL_DB_SERVICE_DIR):
    if str(_import_path) not in sys.path:
        sys.path.insert(0, str(_import_path))

from dots_mocr_vertical_predict import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    RunConfig,
    _append_checkpoint,
    _load_checkpoint,
    _sha256,
    _validate_checkpoint,
    load_vertical_pages,
)
from ocr_content_guards import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    has_suspicious_repetition,
)

MODEL_REVISION = "dc58acc05962cb2ca129c8d3533ab7e5a651cc02"
OCR_PROMPT = "OCR this image as HTML layout blocks with bbox and label."
PROMPT_ID = "qwen3.5-ocr-jp-html-layout-v1"
HTML_PROTOCOL_VERSION = "qwen-html-layout-visible-text-v1"
GENERATION_MODE = "greedy-do-sample-false-v1"
_CODE_FENCE_RE = re.compile(
    r"\A\s*```(?:html)?[ \t]*\r?\n(?P<body>.*)\r?\n```\s*\Z",
    re.DOTALL | re.IGNORECASE,
)
_IGNORED_TAGS = frozenset({"rt", "script", "style"})
_LINE_BREAK_TAGS = frozenset({"br", "p"})
_PLAIN_TEXT_TAGS = frozenset({"br", "div", "p", "rt", "ruby"})


def model_fingerprint(model_path: Path) -> str:
    root = model_path.resolve()
    if not root.is_dir():
        raise ValueError(f"model path is not a directory: {root}")
    required = {
        "chat_template.jinja",
        "config.json",
        "generation_config.json",
        "model.safetensors.index.json",
        "preprocessor_config.json",
        "processor_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    }
    missing = sorted(name for name in required if not (root / name).is_file())
    if missing:
        raise ValueError(f"model snapshot is missing required files: {missing}")
    weights = sorted(root.glob("*.safetensors"))
    if not weights:
        raise ValueError("model snapshot has no safetensors weights")
    digest = hashlib.sha256()
    for path in sorted(root / name for name in required) + weights:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(_sha256(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()


class PredictionEngine(Protocol):
    def generate(self, image_path: Path) -> str: ...


class _LayoutHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._block_tag: str | None = None
        self._block_text: list[str] = []
        self._ignored_depth = 0
        self._outside_text: list[str] = []

    @staticmethod
    def _validate_bbox(value: str) -> None:
        parts = value.split()
        if len(parts) != 4:
            raise ValueError("Qwen HTML layout block has an invalid data-bbox")
        try:
            x1, y1, x2, y2 = (float(part) for part in parts)
        except ValueError as exc:
            raise ValueError(
                "Qwen HTML layout block has a non-numeric data-bbox"
            ) from exc
        if x2 <= x1 or y2 <= y1:
            raise ValueError("Qwen HTML layout block has an invalid data-bbox")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            self._ignored_depth += 1
            return
        attr_map = dict(attrs)
        has_bbox = "data-bbox" in attr_map
        has_label = "data-label" in attr_map
        if has_bbox != has_label:
            raise ValueError(
                "Qwen HTML layout block must have data-bbox and data-label"
            )
        if has_bbox:
            if self._block_tag is not None:
                raise ValueError("Qwen HTML layout blocks must not be nested")
            bbox = attr_map["data-bbox"]
            label = attr_map["data-label"]
            if not isinstance(bbox, str):
                raise ValueError("Qwen HTML layout block has no data-bbox")
            if not isinstance(label, str) or not label.strip():
                raise ValueError("Qwen HTML layout block has no data-label")
            self._validate_bbox(bbox)
            self._block_tag = tag
            self._block_text = []
        if tag == "br" and self._block_tag is not None and not self._ignored_depth:
            self._block_text.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() in _IGNORED_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._block_tag is not None and tag in _LINE_BREAK_TAGS:
            self._block_text.append("\n")
        if tag == self._block_tag:
            text = "".join(self._block_text).strip()
            if text:
                self.blocks.append(text)
            self._block_tag = None
            self._block_text = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._block_tag is not None:
            self._block_text.append(data)
        elif data.strip():
            self._outside_text.append(data)

    def prediction(self) -> tuple[str, int, bool]:
        truncated = self._block_tag is not None
        if self._block_tag is not None:
            text = "".join(self._block_text).strip()
            if text:
                self.blocks.append(text)
            self._block_tag = None
            self._block_text = []
        if self._outside_text:
            raise ValueError("Qwen HTML has visible text outside layout blocks")
        if not self.blocks:
            raise ValueError("Qwen HTML has no non-empty layout blocks")
        return "\n\n".join(self.blocks), len(self.blocks), truncated


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        self.tags.add(tag.lower())

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


class _BboxCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.bboxes: list[tuple[float, float, float, float]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        attr_map = dict(attrs)
        bbox = attr_map.get("data-bbox")
        label = attr_map.get("data-label")
        if bbox is None and label is None:
            return
        if not isinstance(bbox, str) or not isinstance(label, str) or not label.strip():
            raise ValueError("Qwen HTML layout block has invalid bbox metadata")
        _LayoutHtmlParser._validate_bbox(bbox)
        x1, y1, x2, y2 = (float(part) for part in bbox.split())
        self.bboxes.append((x1, y1, x2, y2))


def extract_html_prediction(response: str) -> tuple[str, int, bool]:
    """Return visible text, block count, and whether the last block was cut off."""
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Qwen HTML response is empty")
    match = _CODE_FENCE_RE.fullmatch(response)
    html = match.group("body") if match else response.strip()
    parser = _LayoutHtmlParser()
    try:
        parser.feed(html)
        parser.close()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Qwen HTML response cannot be parsed: {exc}") from exc
    return parser.prediction()


def fallback_markup_tags(response: str) -> tuple[str, ...]:
    """Return format tags not retained by the plain-text OCR contract."""
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Qwen HTML response is empty")
    match = _CODE_FENCE_RE.fullmatch(response)
    html = match.group("body") if match else response.strip()
    parser = _TagCollector()
    parser.feed(html)
    parser.close()
    return tuple(sorted(parser.tags - _PLAIN_TEXT_TAGS))


def has_suspicious_vertical_bbox_order(response: str) -> bool:
    """Detect adjacent narrow columns emitted left-to-right in one row."""
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Qwen HTML response is empty")
    match = _CODE_FENCE_RE.fullmatch(response)
    html = match.group("body") if match else response.strip()
    parser = _BboxCollector()
    parser.feed(html)
    parser.close()
    for first, second in zip(parser.bboxes, parser.bboxes[1:], strict=False):
        first_x1, first_y1, first_x2, first_y2 = first
        second_x1, second_y1, second_x2, second_y2 = second
        if first_x2 - first_x1 > 300 or second_x2 - second_x1 > 300:
            continue
        if abs(first_y1 - second_y1) > 25 or abs(first_y2 - second_y2) > 25:
            continue
        first_center_x = (first_x1 + first_x2) / 2
        second_center_x = (second_x1 + second_x2) / 2
        if first_center_x + 50 < second_center_x:
            return True
    return False


def run_predictions(
    config: RunConfig,
    *,
    engine_factory: Callable[[RunConfig], PredictionEngine],
) -> tuple[int, int]:
    pages = load_vertical_pages(config)
    fingerprint = model_fingerprint(config.model_path)
    checkpoint = _load_checkpoint(
        config.output_path,
        allow_empty_prediction=config.allow_empty_prediction,
    )
    _validate_checkpoint(
        config=config,
        pages=pages,
        checkpoint=checkpoint,
        fingerprint=fingerprint,
    )
    expected_extra = {
        "html_protocol_version": HTML_PROTOCOL_VERSION,
        "generation_mode": GENERATION_MODE,
    }
    for record_id, record in checkpoint.items():
        for field, expected in expected_extra.items():
            if record.get(field) != expected:
                raise ValueError(f"checkpoint id {record_id} {field} mismatch")
        raw_response = record.get("raw_response")
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise ValueError(f"checkpoint id {record_id} has no raw_response")
        if (
            record.get("raw_response_sha256")
            != hashlib.sha256(raw_response.encode()).hexdigest()
        ):
            raise ValueError(f"checkpoint id {record_id} raw_response_sha256 mismatch")

    pending = [page for page in pages if page.record_id not in checkpoint]
    if not pending:
        print(f"complete: {len(pages)}/{len(pages)} pages already checkpointed")
        return 0, len(pages)

    engine = engine_factory(config)
    prompt_sha256 = hashlib.sha256(config.prompt.encode()).hexdigest()
    completed = len(checkpoint)
    for page in pending:
        started_at = time.monotonic()
        response = engine.generate(page.image_path)
        elapsed = time.monotonic() - started_at
        candidate_error: str | None = None
        try:
            prediction, block_count, html_truncated = extract_html_prediction(response)
        except ValueError as exc:
            if not config.allow_empty_prediction:
                raise
            prediction = ""
            block_count = 0
            html_truncated = False
            candidate_error = str(exc)
        markup_tags = fallback_markup_tags(response)
        bbox_order_suspicious = has_suspicious_vertical_bbox_order(response)
        raw_sha256 = hashlib.sha256(response.encode()).hexdigest()
        repetition = has_suspicious_repetition(prediction)
        record = {
            "id": page.record_id,
            "pred": prediction,
            "raw_response": response,
            "raw_response_sha256": raw_sha256,
            "layout_block_count": block_count,
            "html_truncated": html_truncated,
            "fallback_markup_tags": markup_tags,
            "suspicious_vertical_bbox_order": bbox_order_suspicious,
            "suspicious_repetition": repetition,
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
            "html_protocol_version": HTML_PROTOCOL_VERSION,
            "generation_mode": GENERATION_MODE,
            "elapsed_seconds": elapsed,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        if candidate_error is not None:
            record["candidate_error"] = candidate_error
        _append_checkpoint(config.output_path, record)
        completed += 1
        print(
            f"checkpointed {page.record_id}: {completed}/{len(pages)} "
            f"(elapsed={elapsed:.2f}s, chars={len(prediction)}, "
            f"repetition={repetition}, truncated={html_truncated}, "
            f"markup={','.join(markup_tags) or '-'})",
            flush=True,
        )
    return len(pending), completed


class _MpsEngine:
    def __init__(self, config: RunConfig) -> None:
        installed = importlib.metadata.version("transformers")
        if installed != config.engine_version:
            raise ValueError(
                f"transformers version mismatch: {installed} != {config.engine_version}"
            )
        import torch  # pyright: ignore[reportMissingImports]
        from transformers import (  # pyright: ignore[reportMissingImports]
            AutoModelForImageTextToText,
            AutoProcessor,
        )

        if not torch.backends.mps.is_available():
            raise ValueError("PyTorch MPS is unavailable")
        self._torch = torch
        self._processor = AutoProcessor.from_pretrained(
            config.model_path,
            local_files_only=True,
        )
        self._model = (
            AutoModelForImageTextToText.from_pretrained(
                config.model_path,
                local_files_only=True,
                dtype=torch.bfloat16,
            )
            .to("mps")
            .eval()
        )
        self._config = config

    def generate(self, image_path: Path) -> str:
        from PIL import Image
        from transformers import set_seed  # pyright: ignore[reportMissingImports]

        with Image.open(image_path) as source:
            image = source.convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": self._config.prompt},
                ],
            }
        ]
        inputs = self._processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to("mps")
        set_seed(self._config.seed)
        with self._torch.inference_mode():
            output = self._model.generate(
                **inputs,
                max_new_tokens=self._config.max_tokens,
                do_sample=False,
            )
        generated = output[:, inputs["input_ids"].shape[1] :]
        return self._processor.batch_decode(
            generated,
            skip_special_tokens=True,
        )[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-revision", default=MODEL_REVISION)
    parser.add_argument("--engine-version", default="5.12.0")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=8000)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--id", action="append", dest="selected_ids", default=[])
    parser.add_argument("--allow-empty-candidate", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.model_revision != MODEL_REVISION:
        raise ValueError(f"unsupported model revision: {args.model_revision}")
    if args.limit is not None and args.selected_ids:
        raise ValueError("--limit and --id are mutually exclusive")
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")
    if args.max_tokens != 8000:
        raise ValueError("Qwen3.5 OCR screening requires --max-tokens 8000")
    config = RunConfig(
        metadata_path=args.metadata,
        dataset_root=args.dataset_root,
        output_path=args.output,
        model_path=args.model_path,
        model_revision=args.model_revision,
        engine_version=args.engine_version,
        prompt_id=PROMPT_ID,
        prompt=OCR_PROMPT,
        seed=args.seed,
        max_tokens=args.max_tokens,
        temperature=0.0,
        top_p=1.0,
        limit=args.limit,
        selected_ids=tuple(args.selected_ids),
        response_mode="html_layout_v1",
        allow_custom_model_code=False,
        allow_empty_prediction=args.allow_empty_candidate,
    )
    generated, completed = run_predictions(config, engine_factory=_MpsEngine)
    print(f"run complete: generated={generated}, checkpoint_total={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
