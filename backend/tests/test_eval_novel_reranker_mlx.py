from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.eval_novel_reranker_mlx import (
    PageKey,
    build_pair_token_ids,
    load_candidates,
    metrics_for_ranking,
    verify_model,
)


class FakeTokenizer:
    def encode(self, value: str, *, add_special_tokens: bool) -> list[int]:
        assert add_special_tokens is False
        return list(range(1, len(value) + 1))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_build_pair_token_ids_preserves_prefix_and_suffix_when_truncated() -> None:
    ids = build_pair_token_ids(
        FakeTokenizer(),
        prefix_tokens=[101, 102],
        suffix_tokens=[201, 202, 203],
        instruction="instruction",
        query="query",
        document="document" * 100,
        max_length=12,
    )

    assert len(ids) == 12
    assert ids[:2] == [101, 102]
    assert ids[-3:] == [201, 202, 203]


def test_build_pair_token_ids_rejects_too_small_limit() -> None:
    with pytest.raises(ValueError, match="too small"):
        build_pair_token_ids(
            FakeTokenizer(),
            prefix_tokens=[1, 2],
            suffix_tokens=[3, 4],
            instruction="i",
            query="q",
            document="d",
            max_length=4,
        )


def test_metrics_keep_candidate_recall_and_measure_new_order() -> None:
    relevant = {PageKey("book", 1): 3, PageKey("book", 2): 1}
    ranking = [PageKey("book", 1), PageKey("book", 9), PageKey("book", 2)]

    metrics = metrics_for_ranking(ranking, relevant)

    assert metrics["recall_at_5"] == 1.0
    assert metrics["recall_at_10"] == 1.0
    assert metrics["recall_at_30"] == 1.0
    assert metrics["mrr_at_10"] == 1.0
    assert 0.0 < metrics["ndcg_at_10"] <= 1.0


def test_load_candidates_requires_matching_frozen_fixture(tmp_path: Path) -> None:
    result = {
        "schema_version": 1,
        "fixture": {"sha256": "expected"},
        "methods": {
            "method": {
                "aggregate": {"recall_at_30": 1.0},
                "cases": [
                    {
                        "id": "case",
                        "ranking": [
                            {"rank": 1, "book_name": "book", "page_no": 2},
                        ],
                    }
                ],
            }
        },
    }
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(RuntimeError, match="fixture SHA-256"):
        load_candidates(path, expected_fixture_sha256="different", method="method", limit=30)

    candidates, method = load_candidates(path, expected_fixture_sha256="expected", method="method", limit=30)
    assert candidates["case"][0].key == PageKey("book", 2)
    assert method["aggregate"]["recall_at_30"] == 1.0


def test_verify_model_rejects_checkpoint_python_before_hashing(tmp_path: Path) -> None:
    (tmp_path / "modeling_custom.py").write_text("raise RuntimeError", encoding="utf-8")

    with pytest.raises(RuntimeError, match="executable Python"):
        verify_model(tmp_path)


def test_verify_model_rejects_missing_required_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="required model file"):
        verify_model(tmp_path)
