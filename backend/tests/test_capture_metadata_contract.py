"""撮影publicationを入口にメタ更新・復元の既存契約を固定する。"""

import sqlite3
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

import config
from services.kindle_catalog.capture_publication import CapturePublication
from services.kindle_catalog.capture_recovery_record import CaptureRollbackError, read_record
from services.library import capture_metadata
from services.meta_db import db_connection
from services.meta_store import load_meta, update_meta_locked

BOOK = "撮影作品.pdf"
OLD = {"authors": ["既存著者"], "asin": "old-asin", "view_count": 7, "read_state": "reading", "hidden": True}


def publication(tmp_path: Path, source: str = "comic") -> CapturePublication:
    return CapturePublication(
        {"id": "job-id", "title": "撮影作品", "asin": "new-asin", "source": source},
        tmp_path / "inbox/job-id.ready",
        datetime(2026, 9, 8),
    )


def seed(source: str, entry: dict | None) -> None:
    def apply(data: dict) -> None:
        if entry is not None:
            data[BOOK] = deepcopy(entry)
        data["別作品.pdf"] = {"authors": ["別著者"], "asin": "unrelated"}

    update_meta_locked(source, apply)


@pytest.mark.parametrize("source", ["doujin", "comic", "novel"])
@pytest.mark.parametrize("existing", [False, True])
def test_update_and_rollback_preserve_fields_and_source(tmp_data_dir, tmp_path, source, existing):
    seed(source, OLD if existing else None)
    other_source = "novel" if source != "novel" else "comic"
    seed(other_source, OLD)
    before = load_meta(source)
    other_before = load_meta(other_source)
    capture = publication(tmp_path, source)

    capture.update_meta()

    expected = {**(before[BOOK] if existing else {"authors": []}), "asin": "new-asin"}
    assert load_meta(source) == {**before, BOOK: expected}
    assert capture.meta_updated is True
    capture.rollback()
    assert load_meta(source) == before
    assert load_meta(other_source) == other_before


@pytest.mark.parametrize("entry", [None, {"authors": []}, {"authors": [], "asin": "different"}])
def test_existing_images_require_matching_meta_asin(tmp_data_dir, tmp_path, entry):
    seed("comic", entry)
    target = Path(config.get_dirs_by_source("comic")["img"]) / "撮影作品"
    target.mkdir(parents=True)
    image = target / "001.png"
    image.write_bytes(b"old-image")
    before = load_meta("comic")

    with pytest.raises(ValueError, match="同名の別書籍が既にあるため置換できません"):
        publication(tmp_path)

    assert image.read_bytes() == b"old-image"
    assert load_meta("comic") == before


def test_snapshot_is_taken_at_update_not_publication_construction(tmp_data_dir, tmp_path):
    seed("comic", OLD)
    capture = publication(tmp_path)
    changed = {**OLD, "authors": ["更新された著者"], "view_count": 11}
    seed("comic", changed)
    before = load_meta("comic")

    capture.update_meta()
    capture.rollback()

    assert load_meta("comic") == before


@pytest.mark.parametrize("existing", [False, True])
def test_metadata_write_failure_preserves_rows_and_leaves_flag_false(tmp_data_dir, tmp_path, existing):
    seed("comic", OLD if existing else None)
    capture = publication(tmp_path)
    before = load_meta("comic")
    with db_connection() as conn:
        conn.execute(
            "CREATE TRIGGER reject_capture_meta BEFORE INSERT ON books_meta "
            "WHEN NEW.asin='new-asin' BEGIN SELECT RAISE(ABORT, 'meta write failed'); END"
        )

    with pytest.raises(sqlite3.IntegrityError, match="meta write failed"):
        capture.update_meta()

    assert capture.meta_updated is False
    capture.rollback()
    assert load_meta("comic") == before


def test_metadata_restore_failure_still_removes_published_images(tmp_data_dir, tmp_path):
    seed("comic", OLD)
    capture = publication(tmp_path)
    capture.target.mkdir()
    capture.target_published = True
    (capture.target / "001.png").write_bytes(b"published-image")
    capture.update_meta()
    with db_connection() as conn:
        conn.execute(
            "CREATE TRIGGER reject_restore BEFORE INSERT ON books_meta "
            "WHEN NEW.asin='old-asin' BEGIN SELECT RAISE(ABORT, 'meta restore failed'); END"
        )

    with pytest.raises(CaptureRollbackError) as caught:
        capture.rollback()

    assert load_meta("comic")[BOOK]["asin"] == "new-asin"
    assert not capture.target.exists()
    assert isinstance(caught.value.failures[0], sqlite3.IntegrityError)
    assert read_record("job-id").pending.meta_updated is True
    with db_connection() as conn:
        conn.execute("DROP TRIGGER reject_restore")
    capture.rollback()
    assert load_meta("comic")[BOOK] == OLD


@pytest.mark.parametrize("write_fails", [False, True])
def test_library_snapshot_is_detached_and_captured_before_write_result(monkeypatch, write_fails):
    data = {BOOK: deepcopy(OLD)}
    change = capture_metadata.CaptureMetadataChange()

    def update(source, updater):
        assert source == "comic"
        updater(data)
        if write_fails:
            raise OSError("save failed")

    monkeypatch.setattr(capture_metadata, "update_meta_locked", update)
    if write_fails:
        with pytest.raises(OSError, match="save failed"):
            change.apply("comic", BOOK, "new-asin")
    else:
        change.apply("comic", BOOK, "new-asin")
    data[BOOK]["authors"].append("後から変更")

    assert change.previous_entry == OLD
