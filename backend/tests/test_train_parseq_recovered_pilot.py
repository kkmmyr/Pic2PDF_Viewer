from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "train_parseq_recovered_pilot.py"
SPEC = importlib.util.spec_from_file_location("train_parseq_recovered_pilot", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_validate_recovered_payload_accepts_tiny_config() -> None:
    payload = {
        "format_version": 1,
        "state_dict": {"weight": object()},
        "charset_train": "字" * 7141,
        "model_config": {
            "patch_size": [4, 8],
            "embed_dim": 192,
            "enc_num_heads": 3,
            "enc_mlp_ratio": 4,
            "enc_depth": 12,
            "dec_num_heads": 6,
            "dec_mlp_ratio": 4,
            "dec_depth": 1,
            "decode_ar": True,
            "refine_iters": 1,
            "dropout": 0.1,
        },
    }

    config = MODULE.validate_recovered_payload(payload)

    assert config["embed_dim"] == 192


def test_validate_recovered_payload_rejects_standard_parseq() -> None:
    payload = {
        "format_version": 1,
        "state_dict": {"weight": object()},
        "charset_train": "字" * 7141,
        "model_config": {
            "patch_size": [4, 8],
            "embed_dim": 384,
        },
    }

    with pytest.raises(MODULE.PilotError, match="differs from PARSeq Tiny"):
        MODULE.validate_recovered_payload(payload)


def test_pilot_pass_requires_ned_gain_without_accuracy_regression() -> None:
    baseline = MODULE.ValidationMetrics(accuracy=80.0, ned=95.0, loss=0.2)

    assert MODULE.pilot_passed(baseline, MODULE.ValidationMetrics(accuracy=80.0, ned=95.1, loss=0.19))
    assert not MODULE.pilot_passed(baseline, MODULE.ValidationMetrics(accuracy=79.9, ned=95.1, loss=0.19))
    assert not MODULE.pilot_passed(baseline, MODULE.ValidationMetrics(accuracy=80.1, ned=95.0, loss=0.19))
