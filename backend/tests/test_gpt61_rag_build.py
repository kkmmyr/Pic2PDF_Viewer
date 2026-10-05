"""Actual SQLite/Lance publication, interrupted preparation and convergence."""

import copy
import json

import pytest

from services.novel_db import gpt61_body_publication as publication
from services.novel_db import gpt61_rag_build as build
from services.novel_db.connection import with_db
from services.novel_db.lance_store import get_chunks_table, get_summaries_table
from tests.test_gpt61_body_publication import setup_book  # noqa: F401


@pytest.fixture
def published(setup_book, monkeypatch, tmp_path):  # noqa: F811
    db, root, package = setup_book
    text = "公開された新本文。根拠ページに対応する文章です。" * 40
    package["pages"][0]["text"] = package["pages"][0]["artifact"]["text"] = text
    package["package_sha256"] = publication.package_digest(package)
    publication.publish_package(db_path=db, images_root=root, package=package)
    monkeypatch.setattr(build.embedder, "embed_batch", lambda texts: [[1.0] + [0.0] * 1023 for _ in texts])
    with with_db(str(db)) as conn:
        staged = build.prepare_build(conn, package, tmp_path / "cache")
        conn.commit()
        yield conn, package, staged


def test_publish_exact_vectors_noop_and_orphan_cleanup(published):
    conn, package, staged = published
    table = get_chunks_table()
    table.add(
        [
            {
                "chunk_id": 99999,
                "book_name": package["book_name"],
                "page_no": 1,
                "text": "old orphan",
                "char_count": 99,
                "page_count": 1,
                "embedding": [1.0] + [0.0] * 1023,
            }
        ]
    )
    first = build.publish_build(conn, package, staged)
    assert first["status"] == "built"
    assert first["chunks_verified"] == len(staged["chunks"])
    table.checkout_latest()
    version = table.version
    assert build.publish_build(conn, package, staged)["status"] == "already_built"
    assert table.version == version
    assert {r["text"] for r in table.search().to_list()} == {c["text"] for c in staged["chunks"]}
    assert conn.execute("SELECT indexed_at FROM books").fetchone()[0] is not None
    manifest = json.loads(conn.execute("SELECT runtime_manifest_json FROM ocr_runs").fetchone()[0])
    assert manifest["rag_build"]["body_sha256"] == publication.current_digest(conn, package["book_name"])


def test_lance_failure_leaves_unready_and_retry_converges(published, monkeypatch):
    conn, package, staged = published
    table = get_chunks_table()
    original = table.add
    failed = False

    def partial_add(rows):
        nonlocal failed
        if not failed:
            failed = True
            original(rows[:1])
            raise OSError("injected partial Lance write")
        return original(rows)

    monkeypatch.setattr(build, "get_chunks_table", lambda: table)
    monkeypatch.setattr(table, "add", partial_add)
    with pytest.raises(OSError, match="partial Lance"):
        build.publish_build(conn, package, staged)
    assert conn.execute("SELECT indexed_at FROM books").fetchone()[0] is None
    assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0
    assert table.count_rows() == 1
    assert (
        json.loads(conn.execute("SELECT runtime_manifest_json FROM ocr_runs").fetchone()[0])["rag_build"]["state"]
        == "failed"
    )
    assert build.publish_build(conn, package, staged)["status"] == "built"
    assert table.count_rows() == len(staged["chunks"])


def test_source_conflict_and_staged_tamper_fail_before_writes(published):
    conn, package, staged = published
    tampered = copy.deepcopy(staged)
    tampered["vectors"][0][0] = 2.0
    with pytest.raises(ValueError, match="digest mismatch"):
        build.publish_build(conn, package, tampered)
    conn.rollback()
    conn.execute("UPDATE pages SET full_text='different body'")
    conn.commit()
    with pytest.raises(ValueError, match="published body differs"):
        build.publish_build(conn, package, staged)
    assert get_chunks_table().count_rows() == 0


def test_vector_corruption_detected_after_real_publication(published):
    conn, package, staged = published
    build.publish_build(conn, package, staged)
    table = get_chunks_table()
    table.update(values={"embedding": [2.0] + [0.0] * 1023})
    with pytest.raises(ValueError, match="embedding mismatch"):
        build.verify_build(conn, package, staged)


def test_invalidates_derivatives_preserves_other_book(published):
    conn, package, staged = published
    book_id = conn.execute("SELECT id FROM books").fetchone()[0]
    conn.execute("UPDATE books SET summary='old',summary_generated_at='yesterday',catalog_summary='old'")
    conn.execute("UPDATE pages SET main_characters='old character'")
    conn.execute("INSERT INTO book_characters(book_id,name,first_page,page_count) VALUES(?,'old',1,1)", (book_id,))
    other_id = conn.execute(
        "INSERT INTO books(name,pdf_path,images_dir,page_count,summary,indexed_at) "
        "VALUES('other','','',1,'keep','ready')"
    ).lastrowid
    conn.execute("INSERT INTO book_characters(book_id,name,first_page,page_count) VALUES(?,'keep',1,1)", (other_id,))
    conn.commit()
    summaries = get_summaries_table()
    summaries.add(
        [
            {"book_id": book_id, "book_name": package["book_name"], "embedding": [1.0] + [0.0] * 1023},
            {"book_id": other_id, "book_name": "other", "embedding": [1.0] + [0.0] * 1023},
        ]
    )
    build.publish_build(conn, package, staged)
    assert conn.execute("SELECT summary FROM books WHERE id=?", (book_id,)).fetchone()[0] is None
    assert conn.execute("SELECT main_characters FROM pages").fetchone()[0] is None
    assert [r[0] for r in conn.execute("SELECT name FROM book_characters")] == ["keep"]
    assert conn.execute("SELECT summary,indexed_at FROM books WHERE id=?", (other_id,)).fetchone()[:] == (
        "keep",
        "ready",
    )
    summaries.checkout_latest()
    assert summaries.count_rows() == 1
    assert summaries.search().to_list()[0]["book_name"] == "other"


def test_partial_preparation_checkpoint_resume(published, monkeypatch, tmp_path):
    conn, package, _ = published
    # Lower batch size forces interruption between real chunks without changing source.
    monkeypatch.setattr(build, "BATCH_SIZE", 1)
    count = 0

    def intermittent(texts):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("embedding service unavailable")
        return [[1.0] + [0.0] * 1023 for _ in texts]

    monkeypatch.setattr(build.embedder, "embed_batch", intermittent)
    with pytest.raises(OSError):
        build.prepare_build(conn, package, tmp_path / "interrupted")
    conn.commit()
    staged = build.prepare_build(conn, package, tmp_path / "interrupted")
    conn.commit()
    assert count == len(staged["chunks"]) + 1  # First successful batch reused, failed one retried.
    assert build.publish_build(conn, package, staged)["status"] == "built"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0.0])
def test_invalid_embedding_never_publishes(published, monkeypatch, tmp_path, value):
    conn, package, _ = published
    monkeypatch.setattr(build.embedder, "embed_batch", lambda texts: [[value] * 1024 for _ in texts])
    with pytest.raises(ValueError, match="vector"):
        build.prepare_build(conn, package, tmp_path / "invalid")
    assert conn.execute("SELECT indexed_at FROM books").fetchone()[0] is None
    assert get_chunks_table().count_rows() == 0


def test_ready_retry_detects_corruption_and_blocks_rag(published):
    conn, package, staged = published
    build.publish_build(conn, package, staged)
    get_chunks_table().update(values={"embedding": [2.0] + [0.0] * 1023})
    with pytest.raises(ValueError, match="embedding mismatch"):
        build.publish_build(conn, package, staged)
    assert conn.execute("SELECT indexed_at FROM books").fetchone()[0] is None
    assert build.publish_build(conn, package, staged)["status"] == "built"


def test_version_changed_rejects_even_with_valid_staged_hash(published):
    conn, package, staged = published
    changed = copy.deepcopy(staged)
    changed["body_sha256"] = "a" * 64
    changed["staged_sha256"] = publication.digest_json({k: v for k, v in changed.items() if k != "staged_sha256"})
    with pytest.raises(ValueError, match="source/settings conflict"):
        build.publish_build(conn, package, changed)
    assert get_chunks_table().count_rows() == 0


def test_corrupt_checkpoint_fails_closed(published, tmp_path):
    conn, package, _ = published
    cache = tmp_path / "new-cache"
    build.prepare_build(conn, package, cache)
    conn.commit()
    path = next(cache.glob("*/batch-*.json"))
    saved = json.loads(path.read_text())
    saved["vectors"][0][0] = 2.0
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="checkpoint mismatch"):
        build.prepare_build(conn, package, cache)
    assert get_chunks_table().count_rows() == 0


def test_preparation_and_verification_leave_connection_read_only(published, tmp_path):
    conn, package, staged = published
    assert not conn.in_transaction
    build.prepare_build(conn, package, tmp_path / "readonly-cache")
    assert not conn.in_transaction
    build.publish_build(conn, package, staged)
    build.verify_build(conn, package, staged)
    assert not conn.in_transaction


def test_execution_provenance_separates_checkpoints_and_is_sealed(published, tmp_path):
    conn, package, _ = published
    cache = tmp_path / "execution-cache"
    cpu = build.prepare_build(conn, package, cache, execution_metadata={"device": "CPU", "model_digest": "a" * 64})
    gpu = build.prepare_build(conn, package, cache, execution_metadata={"device": "Metal", "model_digest": "a" * 64})
    assert cpu["staged_sha256"] != gpu["staged_sha256"]
    assert len(list(cache.glob("*/staged.json"))) == 2
    changed = copy.deepcopy(gpu)
    changed["execution"]["model_digest"] = "b" * 64
    with pytest.raises(ValueError, match="digest mismatch"):
        build.publish_build(conn, package, changed)
    result = build.publish_build(conn, package, gpu)
    assert result["execution"] == gpu["execution"]


def test_corrupt_page_character_count_cannot_silently_omit_body(published, tmp_path):
    conn, package, staged = published
    conn.execute("UPDATE pages SET char_count=0 WHERE page_no=1")
    conn.commit()
    with pytest.raises(ValueError, match="canonical character count mismatch"):
        build.prepare_build(conn, package, tmp_path / "corrupt-count")
    with pytest.raises(ValueError, match="canonical character count mismatch"):
        build.publish_build(conn, package, staged)
    assert conn.execute("SELECT indexed_at FROM books").fetchone()[0] is None
    assert get_chunks_table().count_rows() == 0
