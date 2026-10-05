"""Canonical QA evidence remains tied to its publication and readiness version."""

from dataclasses import replace

import pytest

from services.novel_db.connection import with_db
from services.novel_db.gpt61_body_publication import current_digest
from services.novel_db.migrations import upgrade_head
from services.novel_db.qa_source_snapshot import assert_qa_sources_current, freeze_qa_sources
from services.novel_db.search import SearchHit


@pytest.fixture
def evidence_db(tmp_data_dir):
    upgrade_head()
    with with_db(tmp_data_dir["NOVEL_DB_PATH"]) as conn:
        for book_id, name, text in [(1, "本A", "本文A。\n<石>は青い。"), (2, "本B", "本文B。石は赤い。")]:
            conn.execute(
                "INSERT INTO books (id,name,pdf_path,images_dir,page_count,indexed_at) VALUES (?,?, '','',1,?)",
                (book_id, name, "2026-10-05T12:00:00"),
            )
            conn.execute(
                "INSERT INTO pages (book_id,page_no,image_path,full_text,char_count,page_type,index_eligible) "
                "VALUES (?,1,?,?,?,'body',1)",
                (book_id, f"{book_id}/001.png", text, len(text)),
            )
            conn.execute(
                "INSERT INTO ocr_runs (id,book_name,engine,model,source_page_count,state,qa_state,"
                "runtime_manifest_json,timing_json) VALUES (?,?, 'gpt61','gpt-6.1',1,'completed','accepted','{}','{}')",
                (book_id, name),
            )
            conn.execute(
                "INSERT INTO ocr_publications (book_id,run_id,action,actor,published_at) VALUES (?,?,'publish','test',?)",
                (book_id, book_id, "2026-10-05T11:00:00"),
            )
        conn.commit()
        hits = [
            SearchHit("本A", 1, "本文A。\n<石>は青い。", False, None, 1.0),
            SearchHit("本B", 1, "本文B。石は赤い。", False, None, 0.9),
        ]
        yield conn, hits


def test_freeze_preserves_full_text_source_order_and_publication_digest(evidence_db):
    conn, hits = evidence_db
    snapshot = freeze_qa_sources(conn, hits)
    assert [(s.source_id, s.book_name, s.page_no, s.text) for s in snapshot.sources] == [
        (0, "本A", 1, hits[0].snippet),
        (1, "本B", 1, hits[1].snippet),
    ]
    assert snapshot.body_versions == {
        name: {"body_sha256": current_digest(conn, name), "indexed_at": "2026-10-05T12:00:00"}
        for name in ("本A", "本B")
    }
    assert_qa_sources_current(conn, snapshot)
    assert not conn.in_transaction


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE pages SET full_text='差し替え本文' WHERE book_id=1",
        "UPDATE ocr_publications SET retired_at='2026-10-05T13:00:00' WHERE book_id=1",
        "UPDATE books SET indexed_at='2026-10-05T13:00:00' WHERE id=1",
        "UPDATE books SET indexed_at=NULL WHERE id=1",
        "UPDATE pages SET index_eligible=0 WHERE book_id=1",
    ],
)
def test_generation_rejects_body_publication_or_readiness_change(evidence_db, mutation):
    conn, hits = evidence_db
    snapshot = freeze_qa_sources(conn, hits)
    original_text = snapshot.sources[0].text
    conn.execute(mutation)
    conn.commit()
    with pytest.raises(ValueError, match="changed"):
        assert_qa_sources_current(conn, snapshot)
    assert snapshot.sources[0].text == original_text


def test_active_ocr_version_change_with_identical_text_is_rejected(evidence_db):
    conn, hits = evidence_db
    snapshot = freeze_qa_sources(conn, hits)
    conn.execute(
        "INSERT INTO ocr_runs (id,book_name,engine,model,source_page_count,state,qa_state,"
        "runtime_manifest_json,timing_json) "
        "SELECT 3,book_name,engine,model,source_page_count,state,qa_state,runtime_manifest_json,timing_json "
        "FROM ocr_runs WHERE id=1"
    )
    conn.execute("UPDATE ocr_publications SET run_id=3 WHERE book_id=1")
    conn.commit()
    assert conn.execute("SELECT full_text FROM pages WHERE book_id=1").fetchone()[0] == snapshot.sources[0].text
    with pytest.raises(ValueError, match="version"):
        assert_qa_sources_current(conn, snapshot)


@pytest.mark.parametrize("invalid", ["duplicate", "highlight", "other_body", "page_zero", "boolean_page", "missing"])
def test_freeze_rejects_untrusted_retrieval_hits(evidence_db, invalid):
    conn, hits = evidence_db
    invalid_hits = {
        "duplicate": [hits[0], hits[0]],
        "highlight": [replace(hits[0], has_highlight=True)],
        "other_body": [replace(hits[0], snippet=hits[1].snippet)],
        "page_zero": [replace(hits[0], page_no=0)],
        "boolean_page": [replace(hits[0], page_no=True)],
        "missing": [replace(hits[0], page_no=2)],
    }[invalid]
    with pytest.raises(ValueError):
        freeze_qa_sources(conn, invalid_hits)
    assert not conn.in_transaction


@pytest.mark.parametrize(
    "mutation", ["UPDATE books SET indexed_at=NULL WHERE id=1", "UPDATE pages SET index_eligible=0 WHERE book_id=1"]
)
def test_freeze_rejects_unavailable_canonical_page(evidence_db, mutation):
    conn, hits = evidence_db
    conn.execute(mutation)
    conn.commit()
    with pytest.raises(ValueError, match="unavailable"):
        freeze_qa_sources(conn, hits)


def test_unselected_book_change_does_not_invalidate_selected_sources(evidence_db):
    conn, hits = evidence_db
    snapshot = freeze_qa_sources(conn, hits[:1])
    conn.execute("UPDATE pages SET full_text='別冊だけ変更' WHERE book_id=2")
    conn.execute("UPDATE books SET indexed_at=NULL WHERE id=2")
    conn.commit()
    assert_qa_sources_current(conn, snapshot)
