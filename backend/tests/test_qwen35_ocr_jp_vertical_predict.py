from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "maintenance"
_SCRIPT_PATH = _SCRIPT_DIR / "qwen35_ocr_jp_vertical_predict.py"
_SPEC = importlib.util.spec_from_file_location("qwen35_ocr_jp_vertical_predict", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
predict = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = predict
_SPEC.loader.exec_module(predict)


def _config(tmp_path: Path) -> Any:
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
    model = tmp_path / "model"
    model.mkdir()
    for name in (
        "chat_template.jinja",
        "config.json",
        "generation_config.json",
        "model.safetensors.index.json",
        "tokenizer.json",
        "preprocessor_config.json",
        "processor_config.json",
        "tokenizer_config.json",
        "model-00001-of-00001.safetensors",
    ):
        (model / name).write_bytes(name.encode())
    return predict.RunConfig(
        metadata_path=metadata,
        dataset_root=dataset,
        output_path=tmp_path / "predictions.jsonl",
        model_path=model,
        model_revision=predict.MODEL_REVISION,
        engine_version="5.12.0",
        prompt_id=predict.PROMPT_ID,
        prompt=predict.OCR_PROMPT,
        seed=0,
        max_tokens=8000,
        temperature=0.0,
        top_p=1.0,
        response_mode="html_layout_v1",
    )


class _Engine:
    def __init__(self, response: str) -> None:
        self.response = response

    def generate(self, image_path: Path) -> str:
        assert image_path.name == "000001.jpg"
        return self.response


def test_model_fingerprint_covers_chat_template(tmp_path: Path) -> None:
    config = _config(tmp_path)
    original = predict.model_fingerprint(config.model_path)

    (config.model_path / "chat_template.jinja").write_text(
        "changed template",
        encoding="utf-8",
    )

    assert predict.model_fingerprint(config.model_path) != original


def test_extract_html_preserves_block_order_and_excludes_ruby_reading() -> None:
    response = """```html
<div data-bbox="700 10 900 900" data-label="Text"><p>右の<ruby>漢字<rt>かんじ</rt></ruby></p></div>
<div data-bbox="400 10 600 900" data-label="Text"><p>左<br>下</p></div>
```"""

    text, block_count, truncated = predict.extract_html_prediction(response)

    assert text == "右の漢字\n\n左\n下"
    assert block_count == 2
    assert truncated is False


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ("plain text", "outside layout blocks"),
        (
            '<div data-bbox="0 0 10" data-label="Text">本文</div>',
            "data-bbox",
        ),
        (
            '<div data-bbox="0 0 10 10">本文</div>',
            "data-bbox and data-label",
        ),
    ],
)
def test_extract_html_rejects_invalid_protocol(response: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        predict.extract_html_prediction(response)


def test_extract_html_marks_token_cutoff_without_repairing_raw_response() -> None:
    response = '<div data-bbox="0 0 10 10" data-label="Text"><p>反復途中'

    text, block_count, truncated = predict.extract_html_prediction(response)

    assert text == "反復途中"
    assert block_count == 1
    assert truncated is True


def test_fallback_markup_tags_ignores_plain_text_tags_and_flags_style() -> None:
    response = """<div data-bbox="0 0 10 10" data-label="Text">
    <p>本文<ruby>漢字<rt>かんじ</rt></ruby><br><i>AI</i></p></div>"""

    assert predict.fallback_markup_tags(response) == ("i",)


def test_vertical_bbox_order_detects_left_before_right_blocks() -> None:
    correct = (
        '<div data-bbox="600 700 900 940" data-label="Text">右</div>'
        '<div data-bbox="300 700 550 940" data-label="Text">左</div>'
    )
    reversed_order = (
        '<div data-bbox="300 700 550 940" data-label="Text">左</div>'
        '<div data-bbox="600 700 900 940" data-label="Text">右</div>'
    )
    different_rows = (
        '<div data-bbox="100 100 400 300" data-label="Text">上</div>'
        '<div data-bbox="600 600 900 900" data-label="Text">下</div>'
    )
    wide_regions = (
        '<div data-bbox="100 500 460 980" data-label="Text">左の広い領域</div>'
        '<div data-bbox="550 500 990 980" data-label="Text">右の広い領域</div>'
    )

    assert not predict.has_suspicious_vertical_bbox_order(correct)
    assert predict.has_suspicious_vertical_bbox_order(reversed_order)
    assert not predict.has_suspicious_vertical_bbox_order(different_rows)
    assert not predict.has_suspicious_vertical_bbox_order(wide_regions)


def test_run_checkpoints_raw_html_provenance_and_repetition(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    repeated = "反復文字列です長さを確保" * 8
    response = f'<div data-bbox="0 0 10 10" data-label="Text"><p>{repeated}</p></div>'

    assert predict.run_predictions(
        config,
        engine_factory=lambda _config: _Engine(response),
    ) == (1, 1)

    record = json.loads(config.output_path.read_text(encoding="utf-8"))
    assert record["pred"] == repeated
    assert record["raw_response"] == response
    assert len(record["raw_response_sha256"]) == 64
    assert record["layout_block_count"] == 1
    assert record["html_truncated"] is False
    assert record["fallback_markup_tags"] == []
    assert record["suspicious_vertical_bbox_order"] is False
    assert record["suspicious_repetition"] is True
    assert record["html_protocol_version"] == predict.HTML_PROTOCOL_VERSION
    assert record["generation_mode"] == predict.GENERATION_MODE

    assert predict.run_predictions(
        config,
        engine_factory=lambda _config: _Engine("should not run"),
    ) == (0, 1)


def test_review_mode_checkpoints_raw_candidate_parse_error(tmp_path: Path) -> None:
    base = _config(tmp_path)
    config = predict.RunConfig(**{**base.__dict__, "allow_empty_prediction": True})
    response = "<div></div>"

    assert predict.run_predictions(
        config,
        engine_factory=lambda _config: _Engine(response),
    ) == (1, 1)

    record = json.loads(config.output_path.read_text(encoding="utf-8"))
    assert record["pred"] == ""
    assert record["raw_response"] == response
    assert record["candidate_error"] == "Qwen HTML has no non-empty layout blocks"


def test_resume_rejects_tampered_raw_html_before_engine_creation(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    response = '<div data-bbox="0 0 10 10" data-label="Text">本文</div>'
    predict.run_predictions(
        config,
        engine_factory=lambda _config: _Engine(response),
    )
    record = json.loads(config.output_path.read_text(encoding="utf-8"))
    record["raw_response"] = response + "改変"
    config.output_path.write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    factory_called = False

    def factory(_config: Any) -> _Engine:
        nonlocal factory_called
        factory_called = True
        return _Engine(response)

    with pytest.raises(ValueError, match="raw_response_sha256 mismatch"):
        predict.run_predictions(config, engine_factory=factory)
    assert not factory_called


def test_main_uses_fixed_official_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(config: Any, *, engine_factory: Any) -> tuple[int, int]:
        captured["config"] = config
        captured["engine_factory"] = engine_factory
        return 1, 1

    monkeypatch.setattr(predict, "run_predictions", fake_run)
    args = [
        "--metadata",
        str(tmp_path / "metadata.jsonl"),
        "--dataset-root",
        str(tmp_path / "dataset"),
        "--output",
        str(tmp_path / "predictions.jsonl"),
        "--model-path",
        str(tmp_path / "model"),
    ]

    assert predict.main(args) == 0
    config = captured["config"]
    assert config.model_revision == predict.MODEL_REVISION
    assert config.prompt == predict.OCR_PROMPT
    assert config.prompt_id == predict.PROMPT_ID
    assert config.max_tokens == 8000
    assert config.temperature == 0.0
    assert config.response_mode == "html_layout_v1"
    assert config.allow_custom_model_code is False
    assert captured["engine_factory"] is predict._MpsEngine


def test_main_rejects_generation_contract_changes(tmp_path: Path) -> None:
    base = [
        "--metadata",
        str(tmp_path / "metadata.jsonl"),
        "--dataset-root",
        str(tmp_path / "dataset"),
        "--output",
        str(tmp_path / "predictions.jsonl"),
        "--model-path",
        str(tmp_path / "model"),
    ]
    with pytest.raises(ValueError, match="max-tokens 8000"):
        predict.main([*base, "--max-tokens", "1024"])
    with pytest.raises(ValueError, match="unsupported model revision"):
        predict.main([*base, "--model-revision", "moving-main"])
