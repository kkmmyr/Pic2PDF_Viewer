from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

from services.novel_db import qwen_dots_worker


def _provenance(engine: str) -> dict[str, object]:
    return {
        "model_revision": f"{engine}-revision",
        "model_fingerprint": f"{engine}-fingerprint",
        "engine_version": "test",
        "prompt_id": f"{engine}-prompt",
        "prompt_sha256": f"{engine}-prompt-sha",
        "seed": 0,
        "max_tokens": 10,
        "temperature": 0.0,
        "top_p": 1.0,
        "response_mode": "test",
    }


def _runtime_manifest(engine: str, revision: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "engine": engine,
        "model_revision": revision,
        "observed_by": "test-inference-process",
    }


def test_composite_worker_emits_auditable_page_after_both_stages(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    dataset_root = tmp_path / "kindle_novel"
    image_path = dataset_root / "images" / "book" / "001.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (20, 30), "white").save(image_path)
    qwen_python = tmp_path / "qwen-python"
    dots_python = tmp_path / "dots-python"
    qwen_python.touch()
    dots_python.touch()
    qwen_model = tmp_path / "qwen-model"
    dots_model = tmp_path / "dots-model"
    qwen_model.mkdir()
    dots_model.mkdir()
    monkeypatch.setenv("OCR_QWEN_PYTHON", str(qwen_python))
    monkeypatch.setenv("OCR_DOTS_PYTHON", str(dots_python))
    monkeypatch.setenv("OCR_QWEN_MODEL_PATH", str(qwen_model))
    monkeypatch.setenv("OCR_DOTS_MODEL_PATH", str(dots_model))
    monkeypatch.setenv("OCR_QWEN_DOTS_ARTIFACT_DIR", str(tmp_path / "artifacts"))

    def fake_stage(stage: str, command: list[str], **_kwargs) -> None:
        if stage != "selector":
            return
        output = Path(command[command.index("--output") + 1])
        metadata = next((tmp_path / "artifacts").glob("*/metadata.jsonl"))
        record_id = json.loads(metadata.read_text(encoding="utf-8"))["id"]
        image_sha256 = qwen_dots_worker._sha256(image_path)
        selected = {
            "id": record_id,
            "pred": "Qwen本文",
            "primary_text": "Qwen本文",
            "external_text": "dots本文",
            "primary_raw_output": '<div data-label="Text" data-bbox="0 0 1000 1000">Qwen本文</div>',
            "external_raw_output": '[{"bbox":[0,0,100,100],"category":"Text","text":"dots本文"}]',
            "primary_provenance": _provenance("qwen"),
            "external_provenance": _provenance("dots"),
            "primary_runtime_manifest": _runtime_manifest("qwen3.5-ocr-jp-2b", qwen_dots_worker.QWEN_MODEL_REVISION),
            "external_runtime_manifest": _runtime_manifest("dots.mocr", qwen_dots_worker.DOTS_MODEL_REVISION),
            "input_sha256": image_sha256,
            "selected_engine": "qwen3.5-ocr-jp-2b",
            "selection_reason": "qwen_clean",
        }
        output.write_text(json.dumps(selected, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(qwen_dots_worker, "_run_stage", fake_stage)

    qwen_dots_worker.run_qwen_dots_review([{"book_name": "book", "page_no": 1, "image_path": str(image_path)}])

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    page = next(event["page"] for event in events if event["event"] == "page")
    assert page["selection_reason"] == "qwen_clean"
    assert page["primary_text"] == "Qwen本文"
    assert page["external_text"] == "dots本文"
    envelope = json.loads(page["raw_output"])
    assert envelope["schema"] == "qwen35-dots-page-v1"
    assert envelope["primary"]["provenance"]["model_revision"] == "qwen-revision"
    assert page["runtime_manifest"]["engine"] == "qwen35_dots_review_v1"
    assert page["runtime_manifest"]["inference_processes"]["qwen"]["engine"] == "qwen3.5-ocr-jp-2b"
    assert page["runtime_manifest"]["inference_processes"]["dots"]["engine"] == "dots.mocr"
    assert "adjudication_worker" in page["runtime_manifest"]


def test_composite_worker_rejects_repetitive_selected_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dataset_root = tmp_path / "kindle_novel"
    image_path = dataset_root / "images" / "book" / "001.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (20, 30), "white").save(image_path)
    for name in ("qwen-python", "dots-python"):
        (tmp_path / name).touch()
    for name in ("qwen-model", "dots-model"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("OCR_QWEN_PYTHON", str(tmp_path / "qwen-python"))
    monkeypatch.setenv("OCR_DOTS_PYTHON", str(tmp_path / "dots-python"))
    monkeypatch.setenv("OCR_QWEN_MODEL_PATH", str(tmp_path / "qwen-model"))
    monkeypatch.setenv("OCR_DOTS_MODEL_PATH", str(tmp_path / "dots-model"))
    monkeypatch.setenv("OCR_QWEN_DOTS_ARTIFACT_DIR", str(tmp_path / "artifacts"))

    def fake_stage(stage: str, command: list[str], **_kwargs) -> None:
        if stage != "selector":
            return
        output = Path(command[command.index("--output") + 1])
        metadata = next((tmp_path / "artifacts").glob("*/metadata.jsonl"))
        record_id = json.loads(metadata.read_text(encoding="utf-8"))["id"]
        repeated = "反復文字列です長さを確保" * 8
        record = {
            "id": record_id,
            "pred": repeated,
            "primary_text": repeated,
            "external_text": "dots本文",
            "primary_raw_output": "<div>raw</div>",
            "external_raw_output": '[{"raw":true}]',
            "primary_provenance": _provenance("qwen"),
            "external_provenance": _provenance("dots"),
            "primary_runtime_manifest": _runtime_manifest("qwen3.5-ocr-jp-2b", qwen_dots_worker.QWEN_MODEL_REVISION),
            "external_runtime_manifest": _runtime_manifest("dots.mocr", qwen_dots_worker.DOTS_MODEL_REVISION),
            "input_sha256": qwen_dots_worker._sha256(image_path),
            "selected_engine": "qwen3.5-ocr-jp-2b",
            "selection_reason": "qwen_clean",
        }
        output.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(qwen_dots_worker, "_run_stage", fake_stage)

    with pytest.raises(ValueError, match="empty or repetitive"):
        qwen_dots_worker.run_qwen_dots_review([{"book_name": "book", "page_no": 1, "image_path": str(image_path)}])


def test_stage_timeout_fails_closed() -> None:
    with pytest.raises(TimeoutError, match="qwen exceeded"):
        qwen_dots_worker._run_stage(
            "qwen",
            [sys.executable, "-c", "import time; time.sleep(5)"],
            timeout_sec=0.05,
            total_pages=1,
        )


def test_settings_preserve_virtualenv_python_symlinks(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    python_link = tmp_path / "venv-python"
    python_link.symlink_to(sys.executable)
    qwen_model = tmp_path / "qwen-model"
    dots_model = tmp_path / "dots-model"
    qwen_model.mkdir()
    dots_model.mkdir()
    monkeypatch.setenv("OCR_QWEN_PYTHON", str(python_link))
    monkeypatch.setenv("OCR_DOTS_PYTHON", str(python_link))
    monkeypatch.setenv("OCR_QWEN_MODEL_PATH", str(qwen_model))
    monkeypatch.setenv("OCR_DOTS_MODEL_PATH", str(dots_model))
    monkeypatch.setenv("OCR_QWEN_DOTS_ARTIFACT_DIR", str(runtime))

    settings = qwen_dots_worker.CompositeSettings.from_env()

    assert settings.qwen_python == python_link
    assert settings.dots_python == python_link
