"""検索方式に依存しない順位評価指標。"""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping, Sequence


def metrics_for_ranking[Key: Hashable](ranked_keys: Sequence[Key], relevant: Mapping[Key, int]) -> dict[str, float]:
    relevant_keys = set(relevant)

    def recall_at(k: int) -> float:
        return len(relevant_keys & set(ranked_keys[:k])) / len(relevant_keys)

    reciprocal_rank = 0.0
    for rank, key in enumerate(ranked_keys[:10], start=1):
        if key in relevant_keys:
            reciprocal_rank = 1.0 / rank
            break

    dcg = sum(
        ((2 ** relevant.get(key, 0)) - 1) / math.log2(rank + 1)
        for rank, key in enumerate(ranked_keys[:10], start=1)
        if key in relevant
    )
    ideal_grades = sorted(relevant.values(), reverse=True)[:10]
    ideal_dcg = sum(((2**grade) - 1) / math.log2(rank + 1) for rank, grade in enumerate(ideal_grades, start=1))
    return {
        "recall_at_5": recall_at(5),
        "recall_at_10": recall_at(10),
        "recall_at_30": recall_at(30),
        "mrr_at_10": reciprocal_rank,
        "ndcg_at_10": dcg / ideal_dcg if ideal_dcg else 0.0,
    }
