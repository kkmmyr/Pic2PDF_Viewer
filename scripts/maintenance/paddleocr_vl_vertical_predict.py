"""Generate resumable PaddleOCR-VL predictions for JSSODa vertical pages.

PaddleOCR and MLX-VLM are intentionally imported only by the real pipeline
factory so validation and checkpoint tests can run in the normal workspace.
Each successful page is appended and fsynced before the next page starts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.request
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Protocol


class PredictionPipeline(Protocol):
    def predict(self, input: str | list[str], **kwargs: Any) -> list[Any]: ...


@dataclass(frozen=True)
class RunConfig:
    metadata_path: Path
    dataset_root: Path
    output_path: Path
    model_revision: str
    prompt_id: str
    seed: int
    server_url: str
    api_model_name: str
    layout_model_dir: Path | None = None
    max_new_tokens: int = 4096
    vl_concurrency: int = 1
    page_batch_size: int = 1
    limit: int | None = None


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
        raise ValueError(f"metadata id {record_id} output_path has no images component") from exc
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


def load_vertical_pages(config: RunConfig) -> list[InputPage]:
    pages: list[InputPage] = []
    seen: set[str] = set()
    with config.metadata_path.open(encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"metadata line {line_number} is invalid JSON: {exc.msg}") from exc
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
                continue
            image_path = _resolve_image(config.dataset_root, record.get("output_path"), record_id=record_id)
            pages.append(
                InputPage(
                    record_id=record_id,
                    image_path=image_path,
                    image_relpath=image_path.relative_to(config.dataset_root.resolve()).as_posix(),
                    image_sha256=_sha256(image_path),
                )
            )
            if config.limit is not None and len(pages) >= config.limit:
                break
    if not pages:
        raise ValueError("metadata vertical scope is empty")
    return pages


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
                raise ValueError(f"checkpoint line {line_number} is invalid JSON: {exc.msg}") from exc
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
) -> None:
    pages_by_id = {page.record_id: page for page in pages}
    extra = sorted(set(checkpoint) - set(pages_by_id))
    if extra:
        raise ValueError(f"checkpoint has metadata-external ids: {extra[:20]}")
    expected = {
        "model_revision": config.model_revision,
        "prompt_id": config.prompt_id,
        "seed": config.seed,
        "vl_concurrency": config.vl_concurrency,
        "page_batch_size": config.page_batch_size,
    }
    for record_id, record in checkpoint.items():
        for field, value in expected.items():
            if record.get(field) != value:
                raise ValueError(f"checkpoint id {record_id} {field} mismatch: {record.get(field)!r} != {value!r}")
        page = pages_by_id[record_id]
        if record.get("input_sha256") != page.image_sha256:
            raise ValueError(f"checkpoint id {record_id} input_sha256 mismatch")
        if record.get("image_relpath") != page.image_relpath:
            raise ValueError(f"checkpoint id {record_id} image_relpath mismatch")


def _extract_prediction(result: Any, *, record_id: str) -> str:
    payload = getattr(result, "json", None)
    if not isinstance(payload, Mapping):
        raise ValueError(f"PaddleOCR result id {record_id} has no JSON mapping")
    result_data = payload.get("res")
    if not isinstance(result_data, Mapping):
        raise ValueError(f"PaddleOCR result id {record_id} has no res object")
    blocks = result_data.get("parsing_res_list")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError(f"PaddleOCR result id {record_id} has no parsing blocks")
    contents: list[str] = []
    for index, block in enumerate(blocks):
        if not isinstance(block, Mapping) or not isinstance(block.get("block_content"), str):
            raise ValueError(f"PaddleOCR result id {record_id} block {index} has no content")
        content = block["block_content"].strip()
        if content:
            contents.append(content)
    prediction = "\n\n".join(contents)
    if not prediction:
        raise ValueError(f"PaddleOCR result id {record_id} is empty")
    return prediction


def _append_checkpoint(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def run_predictions(
    config: RunConfig,
    *,
    pipeline_factory: Callable[[RunConfig], PredictionPipeline],
) -> tuple[int, int]:
    pages = load_vertical_pages(config)
    checkpoint = _load_checkpoint(config.output_path)
    _validate_checkpoint(config=config, pages=pages, checkpoint=checkpoint)
    pending = [page for page in pages if page.record_id not in checkpoint]
    if not pending:
        print(f"complete: {len(pages)}/{len(pages)} pages already checkpointed")
        return 0, len(pages)

    pipeline = pipeline_factory(config)
    completed = len(checkpoint)
    for batch_start in range(0, len(pending), config.page_batch_size):
        batch = pending[batch_start : batch_start + config.page_batch_size]
        started_at = time.monotonic()
        pipeline_input: str | list[str]
        if len(batch) == 1:
            pipeline_input = batch[0].image_path.as_posix()
        else:
            pipeline_input = [page.image_path.as_posix() for page in batch]
        results = pipeline.predict(
            pipeline_input,
            use_queues=False,
            temperature=0.0,
            top_p=1.0,
            max_new_tokens=config.max_new_tokens,
            vlm_extra_args={"seed": config.seed},
        )
        if not isinstance(results, list) or len(results) != len(batch):
            raise ValueError(
                f"PaddleOCR batch expected {len(batch)} pages, got "
                f"{len(results) if isinstance(results, list) else type(results).__name__}"
            )
        elapsed = time.monotonic() - started_at
        for page, result in zip(batch, results, strict=True):
            prediction = _extract_prediction(result, record_id=page.record_id)
            record = {
                "id": page.record_id,
                "pred": prediction,
                "input_sha256": page.image_sha256,
                "image_relpath": page.image_relpath,
                "model_revision": config.model_revision,
                "prompt_id": config.prompt_id,
                "seed": config.seed,
                "vl_concurrency": config.vl_concurrency,
                "page_batch_size": config.page_batch_size,
                "generated_at": datetime.now(UTC).isoformat(),
            }
            _append_checkpoint(config.output_path, record)
            completed += 1
            print(
                f"checkpointed {page.record_id}: {completed}/{len(pages)} "
                f"(batch={elapsed:.2f}s/{len(batch)}, chars={len(prediction)})",
                flush=True,
            )
    return len(pending), completed


def _preflight_server(config: RunConfig) -> None:
    models_url = config.server_url.rstrip("/") + "/v1/models"
    with urllib.request.urlopen(models_url, timeout=10) as response:
        payload = json.load(response)
    models = payload.get("data") if isinstance(payload, dict) else None
    model_ids = {item.get("id") for item in models or [] if isinstance(item, dict) and isinstance(item.get("id"), str)}
    if config.api_model_name not in model_ids:
        raise ValueError(f"MLX-VLM server does not expose requested model: {config.api_model_name}")


def _build_real_pipeline(config: RunConfig) -> PredictionPipeline:
    _preflight_server(config)
    warnings.filterwarnings(
        "ignore",
        message=r"'mlx-vlm-server' does not support `(min|max)_pixels`\.",
        category=UserWarning,
        module=r"paddlex\.inference\.models\.doc_vlm\.predictor",
    )
    from paddleocr import PaddleOCRVL  # pyright: ignore[reportMissingImports]

    return PaddleOCRVL(
        pipeline_version="v1.6",
        layout_detection_model_dir=(config.layout_model_dir.as_posix() if config.layout_model_dir else None),
        vl_rec_backend="mlx-vlm-server",
        vl_rec_server_url=config.server_url,
        vl_rec_max_concurrency=config.vl_concurrency,
        vl_rec_api_model_name=config.api_model_name,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_layout_detection=True,
        use_chart_recognition=False,
        use_seal_recognition=False,
        use_ocr_for_image_block=False,
        format_block_content=False,
        merge_layout_blocks=True,
        use_queues=False,
        device="cpu",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--prompt-id", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--server-url", default="http://127.0.0.1:8111/")
    parser.add_argument("--api-model-name", required=True)
    parser.add_argument("--layout-model-dir", type=Path)
    parser.add_argument("--max-new-tokens", type=int, default=4096)
    parser.add_argument("--vl-concurrency", type=int, default=1)
    parser.add_argument("--page-batch-size", type=int, default=1)
    parser.add_argument("--limit", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")
    if args.max_new_tokens <= 0:
        raise ValueError("--max-new-tokens must be positive")
    if args.vl_concurrency <= 0:
        raise ValueError("--vl-concurrency must be positive")
    if args.page_batch_size <= 0:
        raise ValueError("--page-batch-size must be positive")
    config = RunConfig(
        metadata_path=args.metadata,
        dataset_root=args.dataset_root,
        output_path=args.output,
        model_revision=args.model_revision,
        prompt_id=args.prompt_id,
        seed=args.seed,
        server_url=args.server_url,
        api_model_name=args.api_model_name,
        layout_model_dir=args.layout_model_dir,
        max_new_tokens=args.max_new_tokens,
        vl_concurrency=args.vl_concurrency,
        page_batch_size=args.page_batch_size,
        limit=args.limit,
    )
    generated, completed = run_predictions(config, pipeline_factory=_build_real_pipeline)
    print(f"run complete: generated={generated}, checkpoint_total={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
