from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path

import pytest

from scripts.eval_novel_search import (
    EvalCase,
    PageKey,
    SearchHit,
    _lance_search,
    _sqlite_search,
    build_lance_fts,
    compare_to_baseline,
    evaluate_method,
    load_eligible_pages,
    load_fixture,
    main,
    metrics_for_ranking,
    open_sqlite_read_only,
    reciprocal_rank_fusion,
)

BOOK = "評価用の本"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_source_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE books (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY,
            book_id INTEGER NOT NULL,
            page_no INTEGER NOT NULL,
            full_text TEXT,
            index_eligible INTEGER NOT NULL
        );
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY
        );
        CREATE VIRTUAL TABLE pages_fts USING fts5(
            full_text,
            content='pages',
            content_rowid='id',
            tokenize='trigram'
        );
        INSERT INTO books(id, name) VALUES (1, '評価用の本');
        INSERT INTO pages(id, book_id, page_no, full_text, index_eligible)
        VALUES
            (1, 1, 1, '王族は国のために尽くす義務がある。ベルナードが教えた。', 1),
            (2, 1, 2, 'まったく別の文章。', 1),
            (3, 1, 3, '索引対象外の文章。', 0);
        INSERT INTO chunks(id) VALUES (10), (11);
        INSERT INTO pages_fts(pages_fts) VALUES ('rebuild');
        """
    )
    conn.commit()
    conn.close()


def _case() -> EvalCase:
    return EvalCase(
        case_id="royal_duty",
        query="義務",
        scope_book=BOOK,
        relevant={PageKey(BOOK, 1): 3},
        source="test",
    )


def _fixture_value() -> dict:
    return {
        "schema_version": 1,
        "name": "test-fixture",
        "cases": [
            {
                "id": "royal_duty",
                "query": "義務",
                "scope": {"type": "book", "book_name": BOOK},
                "source": "test",
                "relevant": [{"book_name": BOOK, "page_no": 1, "grade": 3}],
            }
        ],
    }


def test_metrics_for_ranking_calculates_recall_mrr_and_ndcg() -> None:
    relevant = {PageKey("book", 1): 3, PageKey("book", 2): 1}
    hits = [
        SearchHit(PageKey("book", 99), 9.0),
        SearchHit(PageKey("book", 1), 8.0),
        SearchHit(PageKey("book", 2), 7.0),
    ]

    metrics = metrics_for_ranking(hits, relevant)

    expected_dcg = 7 / math.log2(3) + 1 / math.log2(4)
    expected_ideal = 7 / math.log2(2) + 1 / math.log2(3)
    assert metrics["recall_at_5"] == 1.0
    assert metrics["recall_at_10"] == 1.0
    assert metrics["recall_at_30"] == 1.0
    assert metrics["mrr_at_10"] == 0.5
    assert metrics["ndcg_at_10"] == pytest.approx(expected_dcg / expected_ideal)


def test_reciprocal_rank_fusion_rewards_pages_found_by_both_methods() -> None:
    shared = PageKey("book", 1)
    only_first = PageKey("book", 2)
    only_second = PageKey("book", 3)

    fused = reciprocal_rank_fusion(
        [
            [SearchHit(only_first, 10.0), SearchHit(shared, 9.0)],
            [SearchHit(only_second, 20.0), SearchHit(shared, 19.0)],
        ],
        limit=3,
    )

    assert [hit.key for hit in fused] == [shared, only_first, only_second]


def test_fixture_rejects_duplicate_relevant_page(tmp_path: Path) -> None:
    value = _fixture_value()
    value["cases"][0]["relevant"].append({"book_name": BOOK, "page_no": 1, "grade": 2})
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate relevant page"):
        load_fixture(path)


def test_ngram_finds_two_character_query_that_current_trigram_misses(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "novel.db"
    _create_source_db(sqlite_path)
    conn = open_sqlite_read_only(sqlite_path)
    try:
        pages = load_eligible_pages(conn)
        table, info = build_lance_fts(pages, tmp_path / "ngram.lancedb", tokenizer="ngram")

        current = _sqlite_search(conn, _case(), 10)
        challenger = _lance_search(table, _case(), 10)
    finally:
        conn.close()

    assert current == []
    assert [hit.key for hit in challenger] == [PageKey(BOOK, 1)]
    assert info["indexed_rows"] == 2
    assert info["index_size_bytes"] > 0


def test_comparison_reports_rescue_without_recall_regression() -> None:
    case = _case()
    baseline = evaluate_method(
        "baseline",
        [case],
        lambda _case, _limit: [],
        limit=10,
        warmup_runs=0,
        measured_runs=1,
    )
    challenger = evaluate_method(
        "challenger",
        [case],
        lambda _case, _limit: [SearchHit(PageKey(BOOK, 1), 1.0)],
        limit=10,
        warmup_runs=0,
        measured_runs=1,
    )

    comparison = compare_to_baseline(baseline, challenger)

    assert comparison["recall_at_10_regressions"] == []
    assert comparison["zero_hit_rescues"] == ["royal_duty"]
    assert comparison["preliminary_gate_a_pass"] is True


def test_main_keeps_source_read_only_and_omits_source_text(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "novel.db"
    fixture_path = tmp_path / "fixture.json"
    output_path = tmp_path / "result.json"
    work_dir = tmp_path / "indexes"
    _create_source_db(sqlite_path)
    fixture_path.write_text(json.dumps(_fixture_value(), ensure_ascii=False), encoding="utf-8")
    before = _sha256(sqlite_path)

    exit_code = main(
        [
            "--sqlite",
            str(sqlite_path),
            "--fixture",
            str(fixture_path),
            "--output",
            str(output_path),
            "--work-dir",
            str(work_dir),
            "--snapshot-label",
            "test-snapshot",
            "--runs",
            "1",
            "--warmup-runs",
            "0",
        ]
    )

    result = json.loads(output_path.read_text(encoding="utf-8"))
    ranking = result["methods"]["lance_ngram"]["cases"][0]["ranking"]
    assert exit_code == 0
    assert _sha256(sqlite_path) == before
    assert result["protocol"]["result_contains_source_text"] is False
    assert ranking[0]["book_name"] == BOOK
    assert "text" not in ranking[0]
    assert "snippet" not in ranking[0]


def test_repository_fixture_is_frozen_and_meets_minimum_size() -> None:
    fixture = Path(__file__).parents[1] / "scripts" / "fixtures" / "novel_search_eval_v1.json"

    metadata, cases = load_fixture(fixture)

    relevant_books = {key.book_name for case in cases for key in case.relevant}
    assert metadata["label_status"] == "frozen-before-retrieval"
    assert metadata["adoption_eligible"] is True
    assert len(cases) >= 20
    assert len(relevant_books) >= 3
