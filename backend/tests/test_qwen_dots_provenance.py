from __future__ import annotations

from copy import deepcopy

import pytest

from services.novel_db import qwen_dots_provenance
from services.novel_db.ocr_provenance import model_revision_for_engine
from services.novel_db.qwen_dots_worker import COMPOSITE_MODEL_REVISION


def _record() -> dict:
    return {
        "id": "page-1",
        "primary_runtime_manifest": {
            "schema_version": 1,
            "engine": "qwen3.5-ocr-jp-2b",
            "model_revision": "qwen-sha",
            "python": {"executable": "qwen-env/python"},
        },
        "external_runtime_manifest": {
            "schema_version": 1,
            "engine": "dots.mocr",
            "model_revision": "dots-sha",
            "python": {"executable": "dots-env/python"},
        },
    }


def _aggregate(records: list[dict]) -> dict:
    return qwen_dots_provenance.composite_runtime_manifest(
        records,
        qwen_model_revision="qwen-sha",
        dots_model_revision="dots-sha",
        composite_model_revision=COMPOSITE_MODEL_REVISION,
    )


def test_aggregate_preserves_inference_environments_separately(monkeypatch) -> None:
    monkeypatch.setattr(qwen_dots_provenance, "collect_runtime_manifest", lambda *_: {"python": "coordinator-env"})
    record = _record()
    manifest = _aggregate([record, deepcopy(record)])
    assert manifest["inference_processes"]["qwen"] == record["primary_runtime_manifest"]
    assert manifest["inference_processes"]["dots"] == record["external_runtime_manifest"]
    assert manifest["adjudication_worker"] == {"python": "coordinator-env"}
    assert manifest["model_revision"] == COMPOSITE_MODEL_REVISION


@pytest.mark.parametrize("field", ["primary_runtime_manifest", "external_runtime_manifest"])
@pytest.mark.parametrize("change", ["missing", "schema", "engine", "revision", "environment"])
def test_aggregate_rejects_missing_invalid_or_mixed_provenance(field, change) -> None:
    original = _record()
    modified = deepcopy(original)
    if change == "missing":
        modified.pop(field)
    elif change == "schema":
        modified[field]["schema_version"] = True
    elif change == "engine":
        modified[field]["engine"] = "other-engine"
    elif change == "revision":
        modified[field]["model_revision"] = "other-sha"
    else:
        modified[field]["python"] = {"executable": "different-env/python"}
    with pytest.raises(ValueError):
        _aggregate([original, modified])


def test_composite_claim_uses_fixed_revision() -> None:
    assert model_revision_for_engine("qwen35_dots_review_v1", "surya-sha") == COMPOSITE_MODEL_REVISION
    assert model_revision_for_engine("surya2", "surya-sha") == "surya-sha"
