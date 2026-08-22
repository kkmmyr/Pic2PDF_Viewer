from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "dots_mocr_vertical_predict.py"
_SPEC = importlib.util.spec_from_file_location("dots_mocr_vertical_predict", _SCRIPT_PATH)
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
    model_path = tmp_path / "model"
    model_path.mkdir()
    for name, content in {
        "config.json": b"config",
        "tokenizer.json": b"tokenizer",
        "preprocessor_config.json": b"processor",
        "model-00001-of-00001.safetensors": b"weights",
        "modeling_dots_ocr.py": b"model code",
    }.items():
        (model_path / name).write_bytes(content)
    return predict.RunConfig(
        metadata_path=metadata_path,
        dataset_root=dataset_root,
        output_path=tmp_path / "predictions.jsonl",
        model_path=model_path,
        model_revision="revision-sha",
        engine_version="0.6.15",
        prompt_id="dots-mocr-prompt-ocr-v1",
        prompt="Extract the text content from this image.",
    )


class _Engine:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls: list[Path] = []
        self.fail_on_call = fail_on_call

    def generate(self, image_path: Path) -> str:
        self.calls.append(image_path)
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("inference failed")
        return f"本文{len(self.calls)}"


def test_load_vertical_pages_maps_dataset_path_and_hashes_input(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    pages = predict.load_vertical_pages(config)

    assert [page.record_id for page in pages] == ["000001", "000002"]
    assert pages[0].image_relpath == "images/test/000/000001.jpg"
    assert len(pages[0].image_sha256) == 64


def test_model_fingerprint_changes_with_weights(tmp_path: Path) -> None:
    config = _config(tmp_path)
    original = predict.model_fingerprint(config.model_path)

    (config.model_path / "model-00001-of-00001.safetensors").write_bytes(b"changed weights")

    assert predict.model_fingerprint(config.model_path) != original


def test_selected_ids_preserve_requested_order(tmp_path: Path) -> None:
    base = _config(tmp_path)
    config = predict.RunConfig(
        **{
            **base.__dict__,
            "selected_ids": ("000002", "000001"),
        }
    )

    pages = predict.load_vertical_pages(config)

    assert [page.record_id for page in pages] == ["000002", "000001"]


def test_layout_response_concatenates_model_reading_order() -> None:
    response = json.dumps(
        [
            {"bbox": [0, 0, 10, 10], "category": "Text", "text": "右上"},
            {"bbox": [0, 10, 10, 20], "category": "Text", "text": "右下"},
            {"bbox": [10, 0, 20, 20], "category": "Picture"},
        ],
        ensure_ascii=False,
    )

    text, cell_count = predict._extract_prediction(response, response_mode="layout_json")

    assert text == "右上\n\n右下"
    assert cell_count == 3


def test_layout_response_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="invalid JSON"):
        predict._extract_prediction("not-json", response_mode="layout_json")


@pytest.mark.parametrize(
    ("cell", "message"),
    [
        ({"bbox": [0, 0, 10], "category": "Text", "text": "本文"}, "bbox"),
        (
            {
                "bbox": [0, 0, float("nan"), 10],
                "category": "Text",
                "text": "本文",
            },
            "bbox",
        ),
        (
            {"bbox": [0, 0, 10, 10], "category": "Unknown", "text": "本文"},
            "category",
        ),
    ],
)
def test_layout_response_rejects_invalid_cell_contract(cell: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        predict._extract_prediction(json.dumps([cell], ensure_ascii=False), response_mode="layout_json")


def test_run_checkpoints_each_page_and_records_generation_contract(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    engine = _Engine()

    generated, completed = predict.run_predictions(config, engine_factory=lambda _config: engine)

    records = [json.loads(line) for line in config.output_path.read_text(encoding="utf-8").splitlines()]
    assert (generated, completed) == (2, 2)
    assert [record["id"] for record in records] == ["000001", "000002"]
    assert records[0]["pred"] == "本文1"
    assert records[0]["model_revision"] == "revision-sha"
    assert records[0]["engine_version"] == "0.6.15"
    assert records[0]["temperature"] == 0.1
    assert len(records[0]["model_fingerprint"]) == 64
    assert len(records[0]["prompt_sha256"]) == 64


def test_failed_page_keeps_prior_checkpoint_and_resume_skips_it(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    failing_engine = _Engine(fail_on_call=2)

    with pytest.raises(RuntimeError, match="inference failed"):
        predict.run_predictions(config, engine_factory=lambda _config: failing_engine)

    assert len(config.output_path.read_text(encoding="utf-8").splitlines()) == 1
    resumed_engine = _Engine()
    generated, completed = predict.run_predictions(config, engine_factory=lambda _config: resumed_engine)
    assert (generated, completed) == (1, 2)
    assert resumed_engine.calls[0].name == "000002.jpg"


def test_resume_rejects_changed_provenance_before_creating_engine(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    predict.run_predictions(config, engine_factory=lambda _config: _Engine())
    changed = predict.RunConfig(
        **{
            **config.__dict__,
            "max_tokens": 1024,
        }
    )
    factory_called = False

    def factory(_config: Any) -> _Engine:
        nonlocal factory_called
        factory_called = True
        return _Engine()

    with pytest.raises(ValueError, match="max_tokens mismatch"):
        predict.run_predictions(changed, engine_factory=factory)
    assert not factory_called


def test_resume_rejects_changed_model_before_creating_engine(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    predict.run_predictions(config, engine_factory=lambda _config: _Engine())
    (config.model_path / "model-00001-of-00001.safetensors").write_bytes(b"changed weights")
    factory_called = False

    def factory(_config: Any) -> _Engine:
        nonlocal factory_called
        factory_called = True
        return _Engine()

    with pytest.raises(ValueError, match="model_fingerprint mismatch"):
        predict.run_predictions(config, engine_factory=factory)
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
