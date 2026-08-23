"""Generate resumable dots.mocr predictions for JSSODa vertical pages.

MLX-VLM is imported only by the real engine factory so checkpoint and input
validation tests run in the normal workspace. Each successful page is appended
and fsynced before the next page starts. Generated text is preserved without
repetition removal because repetition is a screening failure mode.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

OCR_PROMPT = "Extract the text content from this image."
LAYOUT_CATEGORIES = frozenset(
    {
        "Caption",
        "Footnote",
        "Formula",
        "List-item",
        "Page-footer",
        "Page-header",
        "Picture",
        "Section-header",
        "Table",
        "Text",
        "Title",
    }
)
LAYOUT_PROMPT = """Please output the layout information from the PDF image, including each layout element's bbox, its category, and the corresponding text content within the bbox.

1. Bbox format: [x1, y1, x2, y2]

2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title'].

3. Text Extraction & Formatting Rules:
    - Picture: For the 'Picture' category, the text field should be omitted.
    - Formula: Format its text as LaTeX.
    - Table: Format its text as HTML.
    - All Others (Text, Title, etc.): Format their text as Markdown.

4. Constraints:
    - The output text must be the original text from the image, with no translation.
    - All layout elements must be sorted according to human reading order.

5. Final Output: The entire output must be a single JSON object.
"""


class PredictionEngine(Protocol):
    def generate(self, image_path: Path) -> str: ...


@dataclass(frozen=True)
class RunConfig:
    metadata_path: Path
    dataset_root: Path
    output_path: Path
    model_path: Path
    model_revision: str
    engine_version: str
    prompt_id: str
    prompt: str
    seed: int = 0
    max_tokens: int = 2048
    temperature: float = 0.1
    top_p: float = 1.0
    limit: int | None = None
    selected_ids: tuple[str, ...] = ()
    response_mode: str = "plain_text"
    allow_custom_model_code: bool = False


@dataclass(frozen=True)
class InputPage:
    record_id: str
    image_path: Path
    image_relpath: str
    image_sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_id(value: Any, *, line_number: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"metadata line {line_number} has invalid id: {value!r}")
    return str(value)


def _resolve_image(dataset_root: Path, output_path: Any, *, record_id: str) -> Path:
    if not isinstance(output_path, str) or not output_path.strip():
        raise ValueError(f"metadata id {record_id} has no output_path")
    parts = PurePosixPath(output_path.replace("\\", "/")).parts
    try:
        image_index = parts.index("images")
    except ValueError as exc:
        raise ValueError(
            f"metadata id {record_id} output_path has no images component"
        ) from exc
    relative_parts = parts[image_index:]
    if any(part in {"", ".", ".."} for part in relative_parts):
        raise ValueError(f"metadata id {record_id} has unsafe output_path")
    root = dataset_root.resolve()
    image_path = (root / Path(*relative_parts)).resolve()
    if root not in image_path.parents:
        raise ValueError(f"metadata id {record_id} image escapes dataset root")
    if not image_path.is_file():
        raise ValueError(f"metadata id {record_id} image is missing: {image_path}")
    return image_path


def _parse_vertical_record(
    raw_line: str,
    *,
    line_number: int,
    config: RunConfig,
    seen: set[str],
) -> InputPage | None:
    try:
        record = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"metadata line {line_number} is invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(record, dict) or "id" not in record:
        raise ValueError(f"metadata line {line_number} must be an object with id")
    record_id = _canonical_id(record["id"], line_number=line_number)
    if record_id in seen:
        raise ValueError(f"metadata contains duplicate id: {record_id}")
    seen.add(record_id)
    is_vertical = record.get("is_vertical")
    if not isinstance(is_vertical, bool):
        raise ValueError(f"metadata id {record_id} has non-boolean is_vertical")
    if not is_vertical:
        return None
    image_path = _resolve_image(
        config.dataset_root,
        record.get("output_path"),
        record_id=record_id,
    )
    return InputPage(
        record_id=record_id,
        image_path=image_path,
        image_relpath=image_path.relative_to(config.dataset_root.resolve()).as_posix(),
        image_sha256=_sha256(image_path),
    )


def _iter_vertical_pages(config: RunConfig) -> Iterator[InputPage]:
    seen: set[str] = set()
    page_count = 0
    with config.metadata_path.open(encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            page = _parse_vertical_record(
                raw_line,
                line_number=line_number,
                config=config,
                seen=seen,
            )
            if page is None:
                continue
            page_count += 1
            yield page
            if (
                not config.selected_ids
                and config.limit is not None
                and page_count >= config.limit
            ):
                return


def load_vertical_pages(config: RunConfig) -> list[InputPage]:
    pages = list(_iter_vertical_pages(config))
    if not pages:
        raise ValueError("metadata vertical scope is empty")
    if config.selected_ids:
        if len(set(config.selected_ids)) != len(config.selected_ids):
            raise ValueError("--id contains duplicate ids")
        pages_by_id = {page.record_id: page for page in pages}
        missing = [
            record_id
            for record_id in config.selected_ids
            if record_id not in pages_by_id
        ]
        if missing:
            raise ValueError(f"selected ids are not vertical metadata pages: {missing}")
        return [pages_by_id[record_id] for record_id in config.selected_ids]
    return pages


def model_fingerprint(model_path: Path) -> str:
    root = model_path.resolve()
    if not root.is_dir():
        raise ValueError(f"model path is not a directory: {root}")
    required = ("config.json", "tokenizer.json", "preprocessor_config.json")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ValueError(f"model snapshot is missing required files: {missing}")
    selected_names = {
        *required,
        "generation_config.json",
        "tokenizer_config.json",
        "model.safetensors.index.json",
        "configuration_dots.py",
        "modeling_dots_ocr.py",
        "modeling_dots_vision.py",
    }
    files = sorted(
        path
        for path in root.iterdir()
        if path.is_file()
        and (path.name in selected_names or path.name.endswith(".safetensors"))
    )
    if not any(path.name.endswith(".safetensors") for path in files):
        raise ValueError("model snapshot has no safetensors weights")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(_sha256(path).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"checkpoint line {line_number} is invalid JSON: {exc.msg}"
                ) from exc
            if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                raise ValueError(f"checkpoint line {line_number} has no string id")
            record_id = record["id"]
            if record_id in records:
                raise ValueError(f"checkpoint contains duplicate id: {record_id}")
            if not isinstance(record.get("pred"), str) or not record["pred"].strip():
                raise ValueError(f"checkpoint id {record_id} has empty prediction")
            records[record_id] = record
    return records


def _validate_checkpoint(
    *,
    config: RunConfig,
    pages: list[InputPage],
    checkpoint: Mapping[str, Mapping[str, Any]],
    fingerprint: str,
) -> None:
    pages_by_id = {page.record_id: page for page in pages}
    extra = sorted(set(checkpoint) - set(pages_by_id))
    if extra:
        raise ValueError(f"checkpoint has metadata-external ids: {extra[:20]}")
    expected = {
        "model_revision": config.model_revision,
        "model_fingerprint": fingerprint,
        "engine_version": config.engine_version,
        "prompt_id": config.prompt_id,
        "prompt_sha256": hashlib.sha256(config.prompt.encode()).hexdigest(),
        "seed": config.seed,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "response_mode": config.response_mode,
    }
    for record_id, record in checkpoint.items():
        for field, value in expected.items():
            if (
                field == "response_mode"
                and field not in record
                and value == "plain_text"
            ):
                continue
            if record.get(field) != value:
                raise ValueError(
                    f"checkpoint id {record_id} {field} mismatch: "
                    f"{record.get(field)!r} != {value!r}"
                )
        page = pages_by_id[record_id]
        if record.get("input_sha256") != page.image_sha256:
            raise ValueError(f"checkpoint id {record_id} input_sha256 mismatch")
        if record.get("image_relpath") != page.image_relpath:
            raise ValueError(f"checkpoint id {record_id} image_relpath mismatch")


def _append_checkpoint(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _extract_layout_cell(cell: Any, *, index: int) -> str | None:
    if not isinstance(cell, dict):
        raise ValueError(f"dots.mocr layout cell {index} is not an object")
    category = cell.get("category")
    if category not in LAYOUT_CATEGORIES:
        raise ValueError(f"dots.mocr layout cell {index} has an invalid category")
    bbox = cell.get("bbox")
    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in bbox
        )
        or any(not math.isfinite(value) for value in bbox)
        or bbox[2] <= bbox[0]
        or bbox[3] <= bbox[1]
    ):
        raise ValueError(f"dots.mocr layout cell {index} has an invalid bbox")
    text = cell.get("text")
    if text is None and category == "Picture":
        return None
    if not isinstance(text, str):
        raise ValueError(f"dots.mocr layout cell {index} has no string text")
    return text if text.strip() else None


def _extract_prediction(response: str, *, response_mode: str) -> tuple[str, int | None]:
    if response_mode == "plain_text":
        return response, None
    if response_mode != "layout_json":
        raise ValueError(f"unsupported response mode: {response_mode}")
    try:
        cells = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"dots.mocr layout response is invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(cells, list) or not cells:
        raise ValueError("dots.mocr layout response must be a non-empty JSON list")
    text_items = [
        text
        for index, cell in enumerate(cells)
        if (text := _extract_layout_cell(cell, index=index)) is not None
    ]
    prediction = "\n\n".join(text_items)
    if not prediction:
        raise ValueError("dots.mocr layout response has no text cells")
    return prediction, len(cells)


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
        response = engine.generate(page.image_path)
        elapsed = time.monotonic() - started_at
        if not isinstance(response, str) or not response.strip():
            raise ValueError(f"dots.mocr prediction id {page.record_id} is empty")
        prediction, layout_cell_count = _extract_prediction(
            response, response_mode=config.response_mode
        )
        record = {
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
        }
        if layout_cell_count is not None:
            record["layout_cell_count"] = layout_cell_count
            record["raw_response"] = response
        _append_checkpoint(config.output_path, record)
        completed += 1
        print(
            f"checkpointed {page.record_id}: {completed}/{len(pages)} "
            f"(elapsed={elapsed:.2f}s, chars={len(prediction)})",
            flush=True,
        )
    return len(pending), completed


class _MlxVlmEngine:
    def __init__(self, config: RunConfig) -> None:
        if not config.allow_custom_model_code:
            raise ValueError(
                "dots.mocr requires audited custom model code; "
                "pass --allow-custom-model-code explicitly"
            )
        installed_version = importlib.metadata.version("mlx-vlm")
        if installed_version != config.engine_version:
            raise ValueError(
                f"mlx-vlm version mismatch: {installed_version} != "
                f"{config.engine_version}"
            )
        from mlx_vlm import generate, load  # pyright: ignore[reportMissingImports]
        from mlx_vlm.prompt_utils import (  # pyright: ignore[reportMissingImports]
            apply_chat_template,
        )

        self._generate = generate
        self._config = config
        self._model, self._processor = load(
            config.model_path.as_posix(), trust_remote_code=True
        )
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
        )
        text = getattr(result, "text", None)
        if not isinstance(text, str):
            raise ValueError("MLX-VLM generation result has no string text")
        return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--engine-version", default="0.6.15")
    parser.add_argument("--prompt-mode", choices=("ocr", "layout"), default="ocr")
    parser.add_argument("--prompt-id")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.1)
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
    prompt = OCR_PROMPT if args.prompt_mode == "ocr" else LAYOUT_PROMPT
    prompt_id = args.prompt_id or f"dots-mocr-prompt-{args.prompt_mode}-v1"
    config = RunConfig(
        metadata_path=args.metadata,
        dataset_root=args.dataset_root,
        output_path=args.output,
        model_path=args.model_path,
        model_revision=args.model_revision,
        engine_version=args.engine_version,
        prompt_id=prompt_id,
        prompt=prompt,
        seed=args.seed,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        limit=args.limit,
        selected_ids=tuple(args.selected_ids),
        response_mode="plain_text" if args.prompt_mode == "ocr" else "layout_json",
        allow_custom_model_code=args.allow_custom_model_code,
    )
    generated, completed = run_predictions(config, engine_factory=_MlxVlmEngine)
    print(f"run complete: generated={generated}, checkpoint_total={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
