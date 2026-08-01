from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "build_parseq_lmdb.py"
_SPEC = importlib.util.spec_from_file_location("build_parseq_lmdb", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
builder = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(builder)


def _sample(run_id: int, page_no: int = 1, segment_index: int = 0) -> dict:
    return {
        "run_id": run_id,
        "page_no": page_no,
        "segment_index": segment_index,
    }


def test_split_samples_isolates_validation_by_run() -> None:
    train, validation = builder.split_samples(
        [_sample(1), _sample(2), _sample(2, segment_index=1)],
        validation_run_ids={2},
        forbidden_run_ids={9},
    )

    assert {sample["run_id"] for sample in train} == {1}
    assert {sample["run_id"] for sample in validation} == {2}


def test_split_samples_rejects_final_holdout_leakage() -> None:
    with pytest.raises(ValueError, match="final holdout"):
        builder.split_samples(
            [_sample(1), _sample(9)],
            validation_run_ids={1},
            forbidden_run_ids={9},
        )


def test_split_samples_requires_present_validation_run() -> None:
    with pytest.raises(ValueError, match="absent"):
        builder.split_samples([_sample(1)], validation_run_ids={2}, forbidden_run_ids=set())


def test_estimate_lmdb_size_uses_payload_and_rounds_up(tmp_path: Path) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"a" * 10)
    second.write_bytes(b"b" * 20)

    result = builder.estimate_lmdb_size(
        [
            {"image": str(first), "label": "abc"},
            {"image": str(second), "label": "日本語"},
        ]
    )

    assert result["samples"] == 2
    assert result["image_bytes"] == 30
    assert result["label_bytes"] == 12
    assert result["map_size"] == 256 * 1024**2


def test_estimate_lmdb_size_grows_beyond_minimum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "large.jpg"
    image.write_bytes(b"x")
    monkeypatch.setattr(builder.Path, "stat", lambda _self: type("S", (), {"st_size": 300 * 1024**2})())

    result = builder.estimate_lmdb_size([{"image": str(image), "label": "abcde"}])

    assert result["map_size"] == 512 * 1024**2
