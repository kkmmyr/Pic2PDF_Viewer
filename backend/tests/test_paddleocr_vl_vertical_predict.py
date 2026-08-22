from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "paddleocr_vl_vertical_predict.py"
_SPEC = importlib.util.spec_from_file_location("paddleocr_vl_vertical_predict", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
predict = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = predict
_SPEC.loader.exec_module(predict)


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    _ = path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _config(tmp_path: Path) -> Any:
    dataset_root = tmp_path / "dataset"
    image_dir = dataset_root / "images" / "test" / "000"
    image_dir.mkdir(parents=True)
    (image_dir / "000001.jpg").write_bytes(b"page-one")
    (image_dir / "000002.jpg").write_bytes(b"page-two")
    metadata_path = tmp_path / "metadata.jsonl"
    _write_jsonl(
        metadata_path,
        [
            {
                "id": "000001",
                "output_path": "./data/synthesized/images/test/000/000001.jpg",
                "is_vertical": True,
            },
            {
                "id": "horizontal",
                "output_path": "./data/synthesized/images/test/000/unused.jpg",
                "is_vertical": False,
            },
            {
                "id": "000002",
                "output_path": "./data/synthesized/images/test/000/000002.jpg",
                "is_vertical": True,
            },
        ],
    )
    return predict.RunConfig(
        metadata_path=metadata_path,
        dataset_root=dataset_root,
        output_path=tmp_path / "predictions.jsonl",
        model_revision="revision-sha",
        prompt_id="paddleocr-vl-v1.6-text",
        seed=0,
        server_url="http://127.0.0.1:8111/",
        api_model_name="/models/paddleocr-vl",
    )


class _Result:
    def __init__(self, text: str) -> None:
        self.json = {
            "res": {
                "parsing_res_list": [
                    {"block_content": text},
                    {"block_content": "後半"},
                ]
            }
        }


class _Pipeline:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls: list[tuple[str | list[str], dict[str, Any]]] = []
        self.fail_on_call = fail_on_call

    def predict(self, input: str | list[str], **kwargs: Any) -> list[Any]:
        self.calls.append((input, kwargs))
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("inference failed")
        page_count = len(input) if isinstance(input, list) else 1
        return [_Result(f"本文{len(self.calls)}-{index}") for index in range(page_count)]


def test_load_vertical_pages_maps_dataset_path_and_hashes_input(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    pages = predict.load_vertical_pages(config)

    assert [page.record_id for page in pages] == ["000001", "000002"]
    assert pages[0].image_relpath == "images/test/000/000001.jpg"
    assert len(pages[0].image_sha256) == 64


def test_run_checkpoints_each_page_and_passes_deterministic_generation_args(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    pipeline = _Pipeline()

    generated, completed = predict.run_predictions(config, pipeline_factory=lambda _config: pipeline)

    records = [json.loads(line) for line in config.output_path.read_text(encoding="utf-8").splitlines()]
    assert (generated, completed) == (2, 2)
    assert [record["id"] for record in records] == ["000001", "000002"]
    assert records[0]["pred"] == "本文1-0\n\n後半"
    assert records[0]["model_revision"] == "revision-sha"
    assert records[0]["vl_concurrency"] == 1
    assert records[0]["page_batch_size"] == 1
    assert pipeline.calls[0][1] == {
        "use_queues": False,
        "temperature": 0.0,
        "top_p": 1.0,
        "max_new_tokens": 4096,
        "vlm_extra_args": {"seed": 0},
    }


def test_failed_page_keeps_prior_checkpoint_and_resume_skips_it(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    failing_pipeline = _Pipeline(fail_on_call=2)

    with pytest.raises(RuntimeError, match="inference failed"):
        predict.run_predictions(config, pipeline_factory=lambda _config: failing_pipeline)

    first_records = config.output_path.read_text(encoding="utf-8").splitlines()
    assert len(first_records) == 1
    resumed_pipeline = _Pipeline()
    generated, completed = predict.run_predictions(config, pipeline_factory=lambda _config: resumed_pipeline)
    assert (generated, completed) == (1, 2)
    assert isinstance(resumed_pipeline.calls[0][0], str)
    assert resumed_pipeline.calls[0][0].endswith("000002.jpg")


def test_page_batch_preserves_result_order_and_checkpoints_each_page(
    tmp_path: Path,
) -> None:
    base = _config(tmp_path)
    config = predict.RunConfig(**{**base.__dict__, "page_batch_size": 2})
    pipeline = _Pipeline()

    generated, completed = predict.run_predictions(config, pipeline_factory=lambda _config: pipeline)

    records = [json.loads(line) for line in config.output_path.read_text(encoding="utf-8").splitlines()]
    assert (generated, completed) == (2, 2)
    assert isinstance(pipeline.calls[0][0], list)
    assert records[0]["pred"] == "本文1-0\n\n後半"
    assert records[1]["pred"] == "本文1-1\n\n後半"


def test_resume_rejects_changed_provenance_before_creating_pipeline(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    pipeline = _Pipeline()
    predict.run_predictions(config, pipeline_factory=lambda _config: pipeline)
    changed = predict.RunConfig(
        **{
            **config.__dict__,
            "model_revision": "different-revision",
        }
    )
    factory_called = False

    def factory(_config: Any) -> _Pipeline:
        nonlocal factory_called
        factory_called = True
        return _Pipeline()

    with pytest.raises(ValueError, match="model_revision mismatch"):
        predict.run_predictions(changed, pipeline_factory=factory)
    assert not factory_called


def test_metadata_path_escape_is_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_jsonl(
        config.metadata_path,
        [
            {
                "id": "escape",
                "output_path": "./images/../outside.jpg",
                "is_vertical": True,
            }
        ],
    )

    with pytest.raises(ValueError, match="unsafe output_path"):
        predict.load_vertical_pages(config)
