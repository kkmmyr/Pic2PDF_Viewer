"""Bidirectional summary grounding gate tests."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from services.novel_db import with_db
from services.novel_db.generation_quality import BookFactSheet
from services.novel_db.migrations import upgrade_head
from services.novel_db.search import SearchHit
from services.novel_db.summary_grounding import (
    GroundingError,
    parse_grounding_response,
    split_summary_claims,
    verify_summary_grounding,
)


@pytest.fixture
def grounding_book(tmp_data_dir) -> int:
    upgrade_head()
    with with_db() as conn:
        cursor = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count) VALUES (?, ?, ?, ?)",
            ("grounding-book", "/book.pdf", "/images", 2),
        )
        assert cursor.lastrowid is not None
        book_id = int(cursor.lastrowid)
        conn.executemany(
            """
            INSERT INTO pages
                (book_id, page_no, image_path, full_text, char_count, index_eligible)
            VALUES (?, ?, NULL, ?, ?, 1)
            """,
            [
                (book_id, 1, "茉莉花は試験の課題を引き受けた。", 100),
                (book_id, 2, "茉莉花は手掛かりを見つけ、調査を進めた。", 100),
            ],
        )
        conn.commit()
    return book_id


def _fact_sheet() -> BookFactSheet:
    return BookFactSheet(
        book_facts=("- [page 1] 茉莉花は試験の課題を引き受けた。\n- [page 2] 茉莉花は手掛かりを見つけ、調査を進めた。"),
        character_facts={},
    )


def _hits() -> list[SearchHit]:
    return [
        SearchHit("grounding-book", 1, "", False, None, 1.0),
        SearchHit("grounding-book", 2, "", False, None, 0.9),
    ]


def _passing_response() -> str:
    return json.dumps(
        {
            "claims": [
                {
                    "id": 1,
                    "verdict": "supported",
                    "evidence_pages": [1],
                    "reason": "page 1で課題を引き受けている。",
                },
                {
                    "id": 2,
                    "verdict": "supported",
                    "evidence_pages": [2],
                    "reason": "page 2で調査を進めている。",
                },
            ],
            "coverage": {"verdict": "pass", "missing_facts": []},
        },
        ensure_ascii=False,
    )


def test_split_summary_claims_preserves_unpunctuated_tail() -> None:
    assert split_summary_claims("第一の出来事。第二の出来事！\n結末") == [
        "第一の出来事。",
        "第二の出来事！",
        "結末",
    ]


def test_parse_grounding_response_accepts_complete_supported_result() -> None:
    claims = ["第一の主張。", "第二の主張。"]
    report = parse_grounding_response(
        _passing_response(),
        claims=claims,
        candidate_pages={1: (1,), 2: (2,)},
    )

    assert report.passed is True
    assert report.claims[1].evidence_pages == (2,)


def test_catalog_claims_can_pass_without_reverse_coverage() -> None:
    payload = json.loads(_passing_response())
    payload["coverage"] = {
        "verdict": "fail",
        "missing_facts": [{"pages": [2], "fact": "短縮時に省略した詳細"}],
    }

    report = parse_grounding_response(
        json.dumps(payload, ensure_ascii=False),
        claims=["第一の主張。", "第二の主張。"],
        candidate_pages={1: (1,), 2: (2,)},
        coverage_required=False,
    )

    assert report.passed is True
    assert report.coverage_required is False


def test_parse_rejects_omitted_claim_id() -> None:
    payload = json.loads(_passing_response())
    payload["claims"] = payload["claims"][:1]

    with pytest.raises(GroundingError, match="omitted claim ids"):
        parse_grounding_response(
            json.dumps(payload),
            claims=["第一。", "第二。"],
            candidate_pages={1: (1,), 2: (2,)},
        )


def test_parse_rejects_evidence_page_outside_candidates() -> None:
    payload = json.loads(_passing_response())
    payload["claims"][0]["evidence_pages"] = [99]

    with pytest.raises(GroundingError, match="outside its candidates"):
        parse_grounding_response(
            json.dumps(payload),
            claims=["第一。", "第二。"],
            candidate_pages={1: (1,), 2: (2,)},
        )


def test_verify_passes_and_persists_audit_report(grounding_book: int) -> None:
    summary = "茉莉花は課題を引き受けた。茉莉花は調査を進めた。"
    backend = MagicMock()
    backend.ask.return_value = _passing_response()

    with patch("services.novel_db.summary_grounding.hybrid_search", return_value=_hits()):
        with with_db() as conn:
            report = verify_summary_grounding(
                conn,
                book_id=grounding_book,
                book_name="grounding-book",
                summary=summary,
                fact_sheet=_fact_sheet(),
                writer_model="writer",
                verifier_backend=backend,
                verifier_model="verifier",
            )
            row = conn.execute(
                """
                SELECT content_type, candidate_sha256, writer_model, verifier_model, passed, report_json
                FROM summary_grounding_reports WHERE book_id = ?
                """,
                (grounding_book,),
            ).fetchone()

    assert report.passed is True
    assert row is not None
    assert row[0] == "detailed"
    assert row[1] == hashlib.sha256(summary.encode("utf-8")).hexdigest()
    assert tuple(row[2:5]) == ("writer", "verifier", 1)
    assert json.loads(row[5])["passed"] is True


def test_verify_rejects_unsupported_claim_and_persists_failure(grounding_book: int) -> None:
    payload = json.loads(_passing_response())
    payload["claims"][1].update(
        verdict="unsupported",
        evidence_pages=[],
        reason="戦争後という記述は確認できない。",
    )
    backend = MagicMock()
    backend.ask.return_value = json.dumps(payload, ensure_ascii=False)

    with patch("services.novel_db.summary_grounding.hybrid_search", return_value=_hits()):
        with with_db() as conn:
            with pytest.raises(GroundingError, match="failed claims=2"):
                verify_summary_grounding(
                    conn,
                    book_id=grounding_book,
                    book_name="grounding-book",
                    summary="茉莉花は課題を引き受けた。戦争後に調査を進めた。",
                    fact_sheet=_fact_sheet(),
                    writer_model="writer",
                    verifier_backend=backend,
                    verifier_model="verifier",
                )
            row = conn.execute(
                "SELECT passed, report_json FROM summary_grounding_reports WHERE book_id = ?",
                (grounding_book,),
            ).fetchone()

    assert row is not None
    assert row[0] == 0
    assert json.loads(row[1])["claims"][1]["verdict"] == "unsupported"


def test_verify_invalid_json_is_fail_closed_and_audited(grounding_book: int) -> None:
    backend = MagicMock()
    backend.ask.return_value = "JSONではない応答"

    with patch("services.novel_db.summary_grounding.hybrid_search", return_value=_hits()):
        with with_db() as conn:
            with pytest.raises(GroundingError, match="invalid JSON"):
                verify_summary_grounding(
                    conn,
                    book_id=grounding_book,
                    book_name="grounding-book",
                    summary="茉莉花は課題を引き受けた。茉莉花は調査を進めた。",
                    fact_sheet=_fact_sheet(),
                    writer_model="writer",
                    verifier_backend=backend,
                    verifier_model="verifier",
                )
            row = conn.execute(
                "SELECT passed, report_json FROM summary_grounding_reports WHERE book_id = ?",
                (grounding_book,),
            ).fetchone()

    assert row is not None
    assert row[0] == 0
    assert "invalid JSON" in json.loads(row[1])["error"]
