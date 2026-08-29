from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "maintenance"
_SCRIPT_PATH = _SCRIPT_DIR / "qianfan_ocr_vertical_predict.py"
_SPEC = importlib.util.spec_from_file_location("qianfan_ocr_vertical_predict", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
predict = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = predict
sys.path.insert(0, str(_SCRIPT_DIR))
try:
    _SPEC.loader.exec_module(predict)
finally:
    sys.path.pop(0)


def _args(tmp_path: Path) -> list[str]:
    return [
        "--metadata",
        str(tmp_path / "metadata.jsonl"),
        "--dataset-root",
        str(tmp_path / "dataset"),
        "--output",
        str(tmp_path / "predictions.jsonl"),
        "--model-path",
        str(tmp_path / "model"),
        "--model-revision",
        "revision-sha",
        "--allow-custom-model-code",
    ]


def test_main_uses_fixed_qianfan_screening_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(config: Any, *, engine_factory: Any) -> tuple[int, int]:
        captured["config"] = config
        captured["engine_factory"] = engine_factory
        return 1, 1

    monkeypatch.setattr(predict, "run_predictions", fake_run)

    assert predict.main(_args(tmp_path)) == 0
    config = captured["config"]
    assert config.prompt == "Parse this document to Markdown."
    assert config.prompt_id == "qianfan-ocr-markdown-v1"
    assert config.max_tokens == 4096
    assert config.temperature == 0.0
    assert config.top_p == 1.0
    assert config.response_mode == "plain_text"
    assert config.allow_custom_model_code is True
    assert captured["engine_factory"] is predict._MlxVlmEngine


def test_limit_and_selected_ids_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        predict.main([*_args(tmp_path), "--limit", "1", "--id", "000006"])
