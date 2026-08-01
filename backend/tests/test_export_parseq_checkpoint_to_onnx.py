from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "export_parseq_checkpoint_to_onnx.py"
SPEC = importlib.util.spec_from_file_location("export_parseq_checkpoint_to_onnx", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_calculate_equivalence_accepts_matching_top1_within_thresholds() -> None:
    torch_logits = np.array([[[1.0, 2.0], [3.0, 1.0]]], dtype=np.float32)
    onnx_logits = torch_logits + 0.0001

    result = MODULE.calculate_equivalence(
        name="sample",
        onnx_logits=onnx_logits,
        torch_logits=torch_logits,
        max_abs_threshold=0.001,
        mean_abs_threshold=0.001,
    )

    assert result.passed
    assert result.top1_mismatch_count == 0
    assert result.top1_token_count == 2


def test_calculate_equivalence_rejects_top1_mismatch() -> None:
    torch_logits = np.array([[[1.0, 2.0]]], dtype=np.float32)
    onnx_logits = np.array([[[3.0, 2.0]]], dtype=np.float32)

    result = MODULE.calculate_equivalence(
        name="sample",
        onnx_logits=onnx_logits,
        torch_logits=torch_logits,
        max_abs_threshold=5.0,
        mean_abs_threshold=5.0,
    )

    assert not result.passed
    assert result.top1_mismatch_count == 1


def test_calculate_equivalence_rejects_shape_difference() -> None:
    with pytest.raises(MODULE.ExportError, match="output shapes differ"):
        MODULE.calculate_equivalence(
            name="sample",
            onnx_logits=np.zeros((1, 2, 3), dtype=np.float32),
            torch_logits=np.zeros((1, 3, 3), dtype=np.float32),
            max_abs_threshold=1.0,
            mean_abs_threshold=1.0,
        )
