from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "sarashina_ocr_vertical_predict.py"
_SPEC = importlib.util.spec_from_file_location("sarashina_ocr_vertical_predict", _SCRIPT_PATH)
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
        engine_version="4.57.1",
        prompt_id="sarashina2.2-ocr-image-only-v1",
        prompt='{"repetition_penalty":1.2}',
        seed=42,
        max_tokens=2048,
        temperature=0.0,
        top_p=0.95,
        response_mode="plain_text",
        allow_custom_model_code=True,
    )


class _Engine:
    def generate(self, image_path: Path) -> str:
        assert image_path.name == "000001.jpg"
        return "固定されたOCR本文"


def test_message_content_separates_image_only_and_explicit_prompt() -> None:
    image = object()
    assert predict.message_content(predict.IMAGE_ONLY_PROMPT_ID, "ignored", image) == [
        {"type": "image", "image": image}
    ]
    assert predict.message_content(predict.TRANSCRIPTION_PROMPT_ID, "文字起こしのみ", image) == [
        {"type": "image", "image": image},
        {"type": "text", "text": "文字起こしのみ"},
    ]


def test_run_predictions_records_provenance_and_resumes(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(predict, "model_fingerprint", lambda _: "a" * 64)

    generated, completed = predict.run_predictions(
        config,
        repetition_penalty=1.2,
        engine_factory=lambda _config, _penalty: _Engine(),
    )
    assert (generated, completed) == (1, 1)
    record = json.loads(config.output_path.read_text(encoding="utf-8"))
    assert record["pred"] == "固定されたOCR本文"
    assert record["repetition_penalty"] == 1.2
    assert record["model_revision"] == predict.MODEL_REVISION

    assert predict.run_predictions(
        config,
        repetition_penalty=1.2,
        engine_factory=lambda _config, _penalty: _Engine(),
    ) == (0, 1)


def test_run_predictions_rejects_penalty_change_on_resume(tmp_path, monkeypatch) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(predict, "model_fingerprint", lambda _: "a" * 64)
    predict.run_predictions(
        config,
        repetition_penalty=1.2,
        engine_factory=lambda _config, _penalty: _Engine(),
    )

    with pytest.raises(ValueError, match="repetition_penalty"):
        predict.run_predictions(
            config,
            repetition_penalty=1.3,
            engine_factory=lambda _config, _penalty: _Engine(),
        )
