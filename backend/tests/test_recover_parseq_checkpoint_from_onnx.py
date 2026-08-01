from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "recover_parseq_checkpoint_from_onnx.py"
)
_SPEC = importlib.util.spec_from_file_location("recover_parseq_checkpoint_from_onnx", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_merge_attention_projection_reconstructs_pytorch_order() -> None:
    query_weight = np.arange(6, dtype=np.float32).reshape(3, 2)
    key_value_weight = np.arange(12, dtype=np.float32).reshape(3, 4)
    query_bias = np.arange(2, dtype=np.float32)
    key_value_bias = np.arange(4, dtype=np.float32)

    weight, bias = _MODULE.merge_attention_projection(query_weight, key_value_weight, query_bias, key_value_bias)

    assert weight.shape == (6, 3)
    np.testing.assert_array_equal(weight[:2], query_weight.T)
    np.testing.assert_array_equal(weight[2:], key_value_weight.T)
    np.testing.assert_array_equal(bias, np.concatenate([query_bias, key_value_bias]))


def test_validate_recovered_arrays_rejects_missing_and_non_finite_values() -> None:
    with pytest.raises(_MODULE.RecoveryError, match="missing"):
        _MODULE.validate_recovered_arrays({}, {"weight": (2, 2)})

    with pytest.raises(_MODULE.RecoveryError, match="non-finite"):
        _MODULE.validate_recovered_arrays({"weight": np.array([[np.nan]], dtype=np.float32)}, {"weight": (1, 1)})


def test_calculate_equivalence_requires_top1_and_numeric_thresholds() -> None:
    onnx_logits = np.array([[[1.0, 2.0], [3.0, 1.0]]], dtype=np.float32)
    close_logits = onnx_logits + np.array([[[1e-5, -1e-5], [0.0, 1e-5]]], dtype=np.float32)
    passed = _MODULE.calculate_equivalence("sample", onnx_logits, close_logits, 1e-3, 1e-4)
    assert passed.passed
    assert passed.top1_mismatch_count == 0

    swapped_logits = close_logits.copy()
    swapped_logits[0, 0] = [3.0, 1.0]
    failed = _MODULE.calculate_equivalence("sample", onnx_logits, swapped_logits, 10.0, 10.0)
    assert not failed.passed
    assert failed.top1_mismatch_count == 1
