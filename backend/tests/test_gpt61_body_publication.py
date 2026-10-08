"""Publication identity, version conflict and transactional failure invariants."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from services.novel_db import gpt61_body_publication as publication
from services.novel_db.connection import with_db
from services.novel_db.migrations import upgrade_head


@pytest.fixture
def setup_book(tmp_data_dir):
    upgrade_head()
    db = Path(tmp_data_dir["NOVEL_DB_PATH"])
    root = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"])
    directory = root / "test book"
    directory.mkdir()
    (directory / "001.png").write_bytes(b"source image")
    sha = hashlib.sha256(b"source image").hexdigest()
    artifact = {
        "page_no": 1,
        "page_type": "afterword",
        "text": "あとがき。公開本文です。",
        "image_sha256": sha,
        "model": publication.MODEL,
    }
    with with_db(str(db)) as conn:
        current = publication.current_digest(conn, "test book")
    package = {
        "schema": publication.SCHEMA,
        "package_sha256": "",
        "book_name": "test book",
        "model": publication.MODEL,
        "source_artifact": {"schema": "gpt61-offline-v1", "path": "original.json", "sha256": "a" * 64},
        "quality": {
            "verdict": "accepted",
            "unresolved_body": 0,
            "unresolved_findings": 0,
            "evidence": [{"path": "quality.json", "sha256": "b" * 64}],
        },
        "expected_current_sha256": current,
        "pages": [{**artifact, "final_sha256": "c" * 64, "uncertain_spans": [], "artifact": artifact}],
    }
    package["package_sha256"] = publication.package_digest(package)
    return db, root, package


def publish(setup_book):
    db, root, package = setup_book
    return publication.publish_package(db_path=db, images_root=root, package=package)


def test_repeat_is_noop_and_afterword_is_searchable(setup_book):
    first = publish(setup_book)
    second = publish(setup_book)
    assert first["status"] == "published"
    assert second["status"] == "already_published"
    assert first["run_id"] == second["run_id"]
    assert first["body_published"] and not first["rag_available"]
    db, _, _ = setup_book
    with with_db(str(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ocr_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ocr_publications").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM pages_fts WHERE pages_fts MATCH '公開本文'").fetchone()[0] == 1
    manifest = json.loads((Path(first["backup"]) / "manifest.json").read_text())
    assert manifest["integrity_check"] == "ok"


def test_other_version_requires_current_digest(setup_book):
    publish(setup_book)
    db, root, original = setup_book
    changed = copy.deepcopy(original)
    changed["pages"][0]["text"] = "新本文"
    changed["pages"][0]["artifact"]["text"] = "新本文"
    changed["package_sha256"] = publication.package_digest(changed)
    with pytest.raises(ValueError, match="current publication changed"):
        publication.publish_package(db_path=db, images_root=root, package=changed)


@pytest.mark.parametrize("failure", ["backup", "publish", "verify"])
def test_failure_rolls_back_entire_publication(setup_book, monkeypatch, failure):
    db, _, package = setup_book

    def fail(*args, **kwargs):
        raise OSError("injected failure")

    target = {
        "backup": "create_verified_publication_backup",
        "publish": "publish_pages",
        "verify": "_verify_published",
    }[failure]
    monkeypatch.setattr(publication, target, fail)
    with pytest.raises(OSError):
        publish(setup_book)
    with with_db(str(db)) as conn:
        assert publication.current_digest(conn, package["book_name"]) == package["expected_current_sha256"]
        for table in ["books", "pages", "ocr_runs", "ocr_publications"]:
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_reject_hold_tamper_and_image_change(setup_book):
    db, root, package = setup_book
    held = copy.deepcopy(package)
    held["quality"]["verdict"] = "hold"
    held["package_sha256"] = publication.package_digest(held)
    with pytest.raises(ValueError, match="quality hold"):
        publication.publish_package(db_path=db, images_root=root, package=held)
    tampered = copy.deepcopy(package)
    tampered["pages"][0]["text"] = "tampered"
    with pytest.raises(ValueError, match="digest mismatch"):
        publication.publish_package(db_path=db, images_root=root, package=tampered)
    (root / package["book_name"] / "001.png").write_bytes(b"changed image")
    with pytest.raises(ValueError, match="source image changed"):
        publish(setup_book)


def test_failed_replacement_preserves_existing_body_and_fts(setup_book, monkeypatch):
    first = publish(setup_book)
    db, root, original = setup_book
    changed = copy.deepcopy(original)
    changed["expected_current_sha256"] = first["current_sha256"]
    changed["pages"][0]["text"] = "別版の本文"
    changed["pages"][0]["artifact"]["text"] = "別版の本文"
    changed["package_sha256"] = publication.package_digest(changed)
    original_publish = publication.publish_pages

    def fail_after_page_replacement(*args, **kwargs):
        original_publish(*args, **kwargs)
        raise OSError("after FTS and active publication replacement")

    monkeypatch.setattr(publication, "publish_pages", fail_after_page_replacement)
    with pytest.raises(OSError):
        publication.publish_package(db_path=db, images_root=root, package=changed)
    with with_db(str(db)) as conn:
        assert publication.current_digest(conn, original["book_name"]) == first["current_sha256"]
        assert conn.execute("SELECT COUNT(*) FROM pages_fts WHERE pages_fts MATCH '公開本文'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ocr_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ocr_publications WHERE retired_at IS NULL").fetchone()[0] == 1


def test_explicit_afterword_field_preserves_original_artifact(setup_book):
    db, root, package = setup_book
    page = package["pages"][0]
    original_text = page["text"]
    page["text"] = ""
    page["artifact"]["text"] = ""
    page["artifact"]["other_text"] = original_text
    page["body_text_field"] = "other_text"
    package["package_sha256"] = publication.package_digest(package)
    result = publish(setup_book)
    assert result["body_characters"] == len(original_text)
    with with_db(str(db)) as conn:
        assert conn.execute("SELECT full_text FROM pages").fetchone()[0] == original_text
        raw = json.loads(conn.execute("SELECT raw_output FROM ocr_page_results").fetchone()[0])
        assert raw["artifact"]["text"] == ""
        assert raw["artifact"]["other_text"] == original_text
    assert publish(setup_book)["status"] == "already_published"


@pytest.mark.parametrize("kind,text", [("narrative", ""), ("afterword", "already present")])
def test_other_field_is_not_a_general_fallback(setup_book, kind, text):
    _, _, package = setup_book
    page = package["pages"][0]
    page["page_type"] = page["artifact"]["page_type"] = kind
    page["text"] = page["artifact"]["text"] = text
    page["artifact"]["other_text"] = "reviewed other text"
    page["body_text_field"] = "other_text"
    package["package_sha256"] = publication.package_digest(package)
    with pytest.raises(ValueError, match="empty-text afterword"):
        publish(setup_book)
