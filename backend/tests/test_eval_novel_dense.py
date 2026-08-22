from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from scripts.eval_novel_dense import (
    EvalCase,
    PageKey,
    SearchHit,
    _build_lance_table,
    _dense_search,
    compare_methods,
    main,
    metrics_for_ranking,
    reciprocal_rank_fusion,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case() -> EvalCase:
    return EvalCase(
        case_id="case",
        query="王の誓い",
        scope_book=None,
        relevant={PageKey("本A", 1): 3},
        source="test",
    )


def _method(case: EvalCase, ranking: list[SearchHit]) -> dict:
    metrics = metrics_for_ranking(ranking, case.relevant)
    return {
        "aggregate": {**metrics, "case_count": 1},
        "cases": [{"id": case.case_id, "metrics": metrics}],
    }


def test_metrics_and_rrf_use_page_level_rankings() -> None:
    relevant = {PageKey("本", 1): 3, PageKey("本", 2): 1}
    hits = [
        SearchHit(PageKey("本", 9), 0.9),
        SearchHit(PageKey("本", 1), 0.8),
        SearchHit(PageKey("本", 2), 0.7),
    ]

    metrics = metrics_for_ranking(hits, relevant)
    fused = reciprocal_rank_fusion(
        [
            [SearchHit(PageKey("本", 3), 1.0), SearchHit(PageKey("本", 1), 0.9)],
            [SearchHit(PageKey("本", 4), 1.0), SearchHit(PageKey("本", 1), 0.9)],
        ],
        limit=3,
    )

    expected_dcg = 7 / math.log2(3) + 1 / math.log2(4)
    expected_ideal = 7 / math.log2(2) + 1 / math.log2(3)
    assert metrics["recall_at_10"] == 1.0
    assert metrics["mrr_at_10"] == 0.5
    assert metrics["ndcg_at_10"] == pytest.approx(expected_dcg / expected_ideal)
    assert fused[0].key == PageKey("本", 1)


def test_exact_dense_search_deduplicates_chunks_to_pages(tmp_path: Path) -> None:
    artifact = {
        "chunk_ids": np.asarray([1, 2, 3], dtype=np.int64),
        "book_names": np.asarray(["本A", "本A", "本B"]),
        "page_nos": np.asarray([1, 1, 2], dtype=np.int32),
        "chunk_indices": np.asarray([0, 1, 0], dtype=np.int32),
        "document_vectors": np.asarray([[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]], dtype=np.float32),
    }
    table, info = _build_lance_table(artifact, tmp_path / "dense.lancedb")

    hits = _dense_search(
        table,
        np.asarray([1.0, 0.0], dtype=np.float32),
        _case(),
        limit=2,
        max_chunks_per_page=info["max_chunks_per_page"],
    )

    assert [hit.key for hit in hits] == [PageKey("本A", 1), PageKey("本B", 2)]
    assert info["indexed_chunks"] == 3
    assert info["indexed_pages"] == 2
    assert info["vector_indices"] == []


def test_comparison_requires_improvement_without_recall_regression() -> None:
    case = _case()
    baseline = _method(
        case,
        [SearchHit(PageKey("別", 9), 1.0), SearchHit(PageKey("本A", 1), 0.5)],
    )
    challenger = _method(case, [SearchHit(PageKey("本A", 1), 1.0)])

    comparison = compare_methods(baseline, challenger)

    assert comparison["recall_at_10_regressions"] == []
    assert comparison["mrr_at_10_relative_change"] == 1.0
    assert comparison["pass"] is True


def test_main_keeps_source_read_only_and_omits_vectors(tmp_path: Path) -> None:
    database = tmp_path / "novel.db"
    fixture = tmp_path / "fixture.json"
    artifact = tmp_path / "vectors.npz"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "result.json"
    work_dir = tmp_path / "dense.lancedb"
    conn = sqlite3.connect(database)
    conn.execute("CREATE TABLE marker (value TEXT)")
    conn.execute("INSERT INTO marker VALUES ('unchanged source text')")
    conn.commit()
    conn.close()
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "test",
                "cases": [
                    {
                        "id": "case",
                        "query": "王の誓い",
                        "scope": {"type": "all"},
                        "source": "test",
                        "relevant": [{"book_name": "本A", "page_no": 1, "grade": 3}],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    np.savez_compressed(
        artifact,
        schema_version=np.asarray([1], dtype=np.int16),
        chunk_ids=np.asarray([1, 2], dtype=np.int64),
        book_names=np.asarray(["本A", "本B"]),
        page_nos=np.asarray([1, 2], dtype=np.int32),
        chunk_indices=np.asarray([0, 0], dtype=np.int32),
        document_vectors=np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        query_ids=np.asarray(["case"]),
        query_vectors=np.asarray([[1.0, 0.0]], dtype=np.float32),
    )
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile": "test",
                "fixture": {"sha256": _sha256(fixture)},
                "corpus": {"sqlite_sha256": _sha256(database), "chunk_count": 2},
                "artifact": {
                    "sha256": _sha256(artifact),
                    "contains_source_text": False,
                    "dimension": 2,
                },
                "model": {"model_id": "test/model", "revision": "0" * 40},
                "runtime": {"documents_per_second": 1.0},
            }
        ),
        encoding="utf-8",
    )
    before = _sha256(database)

    exit_code = main(
        [
            "--sqlite",
            str(database),
            "--fixture",
            str(fixture),
            "--artifact",
            str(artifact),
            "--manifest",
            str(manifest),
            "--work-dir",
            str(work_dir),
            "--output",
            str(output),
            "--snapshot-label",
            "test-snapshot",
            "--warmup-runs",
            "0",
            "--runs",
            "1",
        ]
    )

    result = json.loads(output.read_text(encoding="utf-8"))
    ranking = result["methods"]["dense_test"]["cases"][0]["ranking"]
    assert exit_code == 0
    assert _sha256(database) == before
    assert result["protocol"]["result_contains_source_text"] is False
    assert result["safety"]["embedding_in_result"] is False
    assert ranking[0]["book_name"] == "本A"
    assert "embedding" not in ranking[0]
