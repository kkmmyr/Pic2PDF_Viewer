from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "unlimited_ocr_vertical_predict.py"
_SPEC = importlib.util.spec_from_file_location("unlimited_ocr_vertical_predict", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
predict = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(predict)


def _config(tmp_path: Path):
    dataset = tmp_path / "dataset"
    image = dataset / "images" / "test" / "000" / "000001.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    metadata = tmp_path / "metadata.jsonl"
    metadata.write_text(
        json.dumps(
            {
                "id": "000001",
                "output_path": "./data/synthesized/images/test/000/000001.jpg",
                "is_vertical": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return predict.RunConfig(
        metadata_path=metadata,
        dataset_root=dataset,
        output_path=tmp_path / "predictions.jsonl",
        model_path=tmp_path / "model",
        model_revision=predict.MODEL_REVISION,
        engine_version="0.6.15",
        prompt_id=predict.PROMPT_ID,
        prompt=predict.PROMPT,
        seed=0,
        max_tokens=4096,
        temperature=0.0,
        top_p=1.0,
        response_mode="plain_text",
    )


class _Engine:
    def generate(self, image_path: Path) -> str:
        assert image_path.name == "000001.jpg"
        return "固定されたOCR本文\n固定されたOCR本文"


def test_model_fingerprint_covers_processor_code_and_weights(tmp_path: Path) -> None:
    model = tmp_path / "model"
    model.mkdir()
    for name in predict.MODEL_FILES:
        (model / name).write_bytes(name.encode())
    weights = model / "model-00001-of-00001.safetensors"
    weights.write_bytes(b"weights")
    original = predict.model_fingerprint(model)

    (model / "modeling_unlimitedocr.py").write_bytes(b"changed")
    assert predict.model_fingerprint(model) != original

    (model / "modeling_unlimitedocr.py").write_bytes(b"modeling_unlimitedocr.py")
    weights.write_bytes(b"changed weights")
    assert predict.model_fingerprint(model) != original


def test_run_predictions_preserves_repetition_and_resumes(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(predict, "model_fingerprint", lambda _: "a" * 64)

    generated, completed = predict.run_predictions(config, engine_factory=lambda _config: _Engine())
    assert (generated, completed) == (1, 1)
    record = json.loads(config.output_path.read_text(encoding="utf-8"))
    assert record["pred"] == "固定されたOCR本文\n固定されたOCR本文"
    assert record["model_revision"] == predict.MODEL_REVISION
    assert record["prompt_id"] == predict.PROMPT_ID
    assert record["temperature"] == 0.0

    assert predict.run_predictions(config, engine_factory=lambda _config: _Engine()) == (0, 1)


def test_main_rejects_unpinned_revision() -> None:
    with pytest.raises(ValueError, match="unsupported model revision"):
        predict.main(
            [
                "--metadata",
                "metadata.jsonl",
                "--dataset-root",
                "dataset",
                "--output",
                "predictions.jsonl",
                "--model-path",
                "model",
                "--model-revision",
                "moving-main",
            ]
        )
