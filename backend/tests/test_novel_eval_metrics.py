from __future__ import annotations

import math

import pytest

from scripts.eval_novel_dense import PageKey as DensePageKey
from scripts.eval_novel_dense import SearchHit as DenseSearchHit
from scripts.eval_novel_dense import metrics_for_ranking as dense_metrics_for_ranking
from scripts.eval_novel_reranker_mlx import PageKey as RerankerPageKey
from scripts.eval_novel_reranker_mlx import metrics_for_ranking as reranker_metrics_for_ranking
from scripts.eval_novel_search import PageKey as SearchPageKey
from scripts.eval_novel_search import SearchHit as SearchSearchHit
from scripts.eval_novel_search import metrics_for_ranking as search_metrics_for_ranking
from scripts.novel_eval_metrics import metrics_for_ranking


def test_metrics_for_ranking_matches_independent_expected_fixture() -> None:
    relevant = {"best": 3, "low": 1}
    ranking = ["irrelevant", "best", "low"]

    metrics = metrics_for_ranking(ranking, relevant)

    expected_dcg = 7 / math.log2(3) + 1 / math.log2(4)
    expected_ideal = 7 / math.log2(2) + 1 / math.log2(3)
    assert metrics == {
        "recall_at_5": 1.0,
        "recall_at_10": 1.0,
        "recall_at_30": 1.0,
        "mrr_at_10": 0.5,
        "ndcg_at_10": pytest.approx(expected_dcg / expected_ideal),
    }


def test_public_embedding_export_symbols_remain_star_importable() -> None:
    namespace: dict[str, object] = {}

    exec("from scripts.export_novel_embeddings_mlx import *", namespace)

    assert {"DEFAULT_TASK", "PROFILES", "Chunk", "EvalQuery", "MlxEmbedder", "verify_model"} <= set(namespace)
    assert namespace["DEFAULT_TASK"] == "Given a web search query, retrieve relevant passages that answer the query"


def test_all_metrics_adapters_keep_duplicate_and_cutoff_semantics() -> None:
    expected_dcg = 7 / math.log2(3) + 7 / math.log2(4) + 3 / math.log2(6)
    expected_ideal = 7 / math.log2(2) + 3 / math.log2(3) + 1 / math.log2(4)
    expected = {
        "recall_at_5": 2 / 3,
        "recall_at_10": 2 / 3,
        "recall_at_30": 1.0,
        "mrr_at_10": 0.5,
        "ndcg_at_10": expected_dcg / expected_ideal,
    }

    def ranking(page_key: object) -> list[object]:
        return [
            page_key.__class__("book", 99),
            page_key.__class__("book", 1),
            page_key.__class__("book", 1),
            page_key.__class__("book", 98),
            page_key.__class__("book", 2),
            *[page_key.__class__("book", page_no) for page_no in range(10, 34)],
            page_key.__class__("book", 3),
        ]

    def relevant(page_key: object) -> dict[object, int]:
        return {
            page_key.__class__("book", 1): 3,
            page_key.__class__("book", 2): 2,
            page_key.__class__("book", 3): 1,
        }

    search_keys = ranking(SearchPageKey("book", 0))
    dense_keys = ranking(DensePageKey("book", 0))
    reranker_keys = ranking(RerankerPageKey("book", 0))

    actual = (
        search_metrics_for_ranking(
            [SearchSearchHit(key, float(index)) for index, key in enumerate(search_keys)],
            relevant(SearchPageKey("book", 0)),
        ),
        dense_metrics_for_ranking(
            [DenseSearchHit(key, float(index)) for index, key in enumerate(dense_keys)],
            relevant(DensePageKey("book", 0)),
        ),
        reranker_metrics_for_ranking(reranker_keys, relevant(RerankerPageKey("book", 0))),
    )

    for metrics in actual:
        assert metrics == pytest.approx(expected)
