"""Kindle キャプチャジョブと Linux inbox 取込テスト。"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

import config
from services.kindle_catalog import capture_jobs as capture_jobs_service
from services.kindle_catalog.capture_jobs import (
    claim,
    complete,
    create,
    heartbeat,
    update_state,
)
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.migrations import upgrade_head
from services.kindle_catalog.repository import list_books
from services.meta_store import load_meta, update_meta_locked
from utils.dt import JST


def _capture_manifest(job: dict, image_path: Path) -> dict:
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    with Image.open(image_path) as image:
        image.load()
        width, height = image.size
    return {
        "manifest_version": 2,
        "job_id": job["id"],
        "asin": job["asin"],
        "source": job["source"],
        "capture": {
            "policy_version": "kindle-completeness-v1",
            "termination_reason": "expected_screen_count_confirmed",
            "end_of_book_proven": True,
            "captured_screens": 1,
            "expected_screens": 1,
            "direction": "left",
            "layout": "spread",
            "crop_bounds": [0, 0, width, height],
            "image_size": [width, height],
            "last_saved_file": "001.png",
            "unchanged_observation_windows": 2,
            "termination_unchanged_windows": 2,
            "observation_timeout_seconds": 5.0,
            "retry_limit": 1,
            "turn_commands": 2,
            "successful_transitions": 0,
            "retry_commands": 1,
            "opposite_direction_commands": 0,
            "canary": {
                "policy_version": "kindle-capture-canary-v1",
                "passed": True,
                "dimensions": [width, height],
                "crop_bounds": [0, 0, width, height],
                "first_sha256": "a" * 64,
                "second_sha256": "b" * 64,
                "mean_difference": 1.0,
                "changed_ratio": 0.1,
            },
        },
        "quality": {
            "schema_version": 1,
            "policy_version": "kindle-image-qa-v1",
            "warning_policy_version": "kindle-image-warning-v1",
            "outcome": "passed",
            "page_count": 1,
            "dimensions": [width, height],
            "findings": [],
            "overlay_detector": {
                "policy_version": "kindle-repeated-overlay-v1",
                "passed": True,
                "sampled_page_count": 1,
                "candidate_count": 0,
                "blocking_candidate_count": 0,
            },
        },
        "files": [
            {
                "name": "001.png",
                "sha256": digest,
                "width": width,
                "height": height,
                "size": image_path.stat().st_size,
            }
        ],
    }


def _seed_book() -> None:
    with with_db() as conn:
        conn.execute(
            "INSERT INTO books(asin,title,title_normalized,category,book_type) "
            "VALUES ('B000CAPTURE','キャプチャ作品','キャプチャ作品','kindle','comic')"
        )


def _seed_identity() -> None:
    with with_db() as conn:
        author_id = conn.execute("INSERT INTO authors(name,name_key) VALUES ('著者A','著者a')").lastrowid
        conn.execute(
            "INSERT INTO book_authors(asin,author_id,sort_order) VALUES (?,?,0)",
            ("B000CAPTURE", author_id),
        )
        series_id = conn.execute(
            "INSERT INTO series(name,author,author_key) VALUES ('シリーズA','著者A','著者a')"
        ).lastrowid
        conn.execute(
            """
            INSERT INTO book_series(
                asin,series_id,volume_number,volume_label,detection_method,
                is_manually_edited
            ) VALUES (?,?,10.0,'10','test',0)
            """,
            ("B000CAPTURE", series_id),
        )


def _prepare_ready_job(inbox: Path, make_png) -> dict:
    upgrade_head()
    _seed_book()
    job = create("B000CAPTURE", "comic", "left", 1)
    claim("windows-1")
    update_state(job["id"], "windows-1", "waiting_user")
    update_state(job["id"], "windows-1", "capturing")

    ready = inbox / f"{job['id']}.ready"
    image_path = ready / "images" / "001.png"
    make_png(str(image_path))
    (ready / "manifest.json").write_text(
        json.dumps(_capture_manifest(job, image_path), ensure_ascii=False),
        encoding="utf-8",
    )
    update_state(job["id"], "windows-1", "awaiting_files", captured_screens=1)
    return job


def test_capture_job_claim_and_ready_package_publish(tmp_data_dir, tmp_path, monkeypatch, make_png):
    inbox = tmp_path / "capture-inbox"
    monkeypatch.setattr(config, "KINDLE_CAPTURE_INBOX_DIR", str(inbox))
    upgrade_head()
    _seed_book()
    job = create("B000CAPTURE", "comic", "left", 1)

    claimed = claim("windows-1")

    assert claimed is not None
    assert claimed["id"] == job["id"]
    assert claim("windows-1")["id"] == job["id"]
    update_state(job["id"], "windows-1", "waiting_user")
    update_state(job["id"], "windows-1", "capturing")

    ready = inbox / f"{job['id']}.ready"
    image_path = ready / "images" / "001.png"
    make_png(str(image_path))
    (ready / "manifest.json").write_text(
        json.dumps(_capture_manifest(job, image_path), ensure_ascii=False),
        encoding="utf-8",
    )
    update_state(job["id"], "windows-1", "awaiting_files", captured_screens=1)

    result = complete(job["id"], "windows-1")

    assert result["status"] == "succeeded"
    assert Path(tmp_data_dir["COMIC_IMAGES_DIR"], "キャプチャ作品", "001.png").is_file()
    assert load_meta("comic")["キャプチャ作品.pdf"]["asin"] == "B000CAPTURE"
    assert Path(inbox, "processed", job["id"], "manifest.json").is_file()


def test_capture_job_replaces_same_asin_and_keeps_generation_backup(
    tmp_data_dir,
    tmp_path,
    monkeypatch,
    make_png,
):
    inbox = tmp_path / "capture-inbox"
    monkeypatch.setattr(config, "KINDLE_CAPTURE_INBOX_DIR", str(inbox))
    target = Path(tmp_data_dir["COMIC_IMAGES_DIR"], "キャプチャ作品")
    target.mkdir(parents=True)
    old_image = target / "001.png"
    old_image.write_bytes(b"old-image")

    def seed_meta(data):
        data["キャプチャ作品.pdf"] = {
            "authors": ["既存著者"],
            "asin": "B000CAPTURE",
            "read_state": "reading",
        }

    update_meta_locked("comic", seed_meta)
    job = _prepare_ready_job(inbox, make_png)

    result = complete(job["id"], "windows-1")

    assert result["status"] == "succeeded"
    assert (target / "001.png").read_bytes() != b"old-image"
    backups = list(
        Path(config.DATA_DIR, ".capture-replacement-backup").glob(f"*_{job['id'][:8]}/comic-キャプチャ作品/001.png")
    )
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"old-image"
    meta = load_meta("comic")["キャプチャ作品.pdf"]
    assert meta["asin"] == "B000CAPTURE"
    assert meta["authors"] == ["既存著者"]
    assert meta["read_state"] == "reading"


def test_capture_job_rejects_same_title_with_different_asin(
    tmp_data_dir,
    tmp_path,
    monkeypatch,
    make_png,
):
    inbox = tmp_path / "capture-inbox"
    monkeypatch.setattr(config, "KINDLE_CAPTURE_INBOX_DIR", str(inbox))
    target = Path(tmp_data_dir["COMIC_IMAGES_DIR"], "キャプチャ作品")
    target.mkdir(parents=True)
    (target / "001.png").write_bytes(b"other-book")

    def seed_meta(data):
        data["キャプチャ作品.pdf"] = {
            "authors": [],
            "asin": "B000DIFFERENT",
        }

    update_meta_locked("comic", seed_meta)
    job = _prepare_ready_job(inbox, make_png)

    with pytest.raises(ValueError, match="別書籍"):
        complete(job["id"], "windows-1")

    assert (target / "001.png").read_bytes() == b"other-book"
    assert Path(inbox, f"{job['id']}.ready", "manifest.json").is_file()


def test_capture_package_rejects_path_traversal_filename(tmp_data_dir, tmp_path, monkeypatch, make_png):
    inbox = tmp_path / "capture-inbox"
    monkeypatch.setattr(config, "KINDLE_CAPTURE_INBOX_DIR", str(inbox))
    upgrade_head()
    _seed_book()
    job = create("B000CAPTURE", "comic", "left", None)
    claim("windows-1")
    update_state(job["id"], "windows-1", "waiting_user")
    update_state(job["id"], "windows-1", "capturing")
    update_state(job["id"], "windows-1", "awaiting_files")
    ready = inbox / f"{job['id']}.ready"
    make_png(str(ready / "images" / "001.png"))
    manifest = _capture_manifest(job, ready / "images" / "001.png")
    manifest["files"][0]["name"] = "../001.png"
    (ready / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    try:
        complete(job["id"], "windows-1")
    except ValueError as exc:
        assert "ファイル名" in str(exc)
    else:
        raise AssertionError("path traversal must be rejected")


def test_claim_returns_identity_and_new_automatic_state_path(tmp_data_dir):
    upgrade_head()
    _seed_book()
    _seed_identity()
    job = create("B000CAPTURE", "novel", "left", None)

    claimed = claim("windows-auto")

    assert claimed is not None
    assert claimed["identity"] == {
        "asin": "B000CAPTURE",
        "title": "キャプチャ作品",
        "title_normalized": "キャプチャ作品",
        "authors": ["著者A"],
        "series_name": "シリーズA",
        "volume_number": 10.0,
        "volume_label": "10",
    }
    assert claimed["heartbeat_at"] is not None

    update_state(job["id"], "windows-auto", "locating_book")
    books = list_books(
        q=None,
        book_type=None,
        ownership=None,
        capture_state=None,
        page=1,
        page_size=50,
    )
    assert books["items"][0]["capture_state"] == "capture_pending"
    update_state(job["id"], "windows-auto", "downloading")
    update_state(job["id"], "windows-auto", "positioning")
    capturing = update_state(job["id"], "windows-auto", "capturing")
    progress = update_state(
        job["id"],
        "windows-auto",
        "capturing",
        captured_screens=7,
    )
    awaiting = update_state(
        job["id"],
        "windows-auto",
        "awaiting_files",
        captured_screens=12,
    )

    assert capturing["started_at"] is not None
    assert progress["started_at"] == capturing["started_at"]
    assert progress["captured_screens"] == 7
    assert awaiting["captured_screens"] == 12


def test_create_rejects_second_unfinished_job_for_different_asin(tmp_data_dir):
    upgrade_head()
    _seed_book()
    with with_db() as conn:
        conn.execute(
            "INSERT INTO books(asin,title,title_normalized,category,book_type) "
            "VALUES ('B000OTHER','別作品','別作品','kindle','novel')"
        )
    first = create("B000CAPTURE", "comic", "left", None)

    with pytest.raises(ValueError, match="別の未完了"):
        create("B000OTHER", "novel", "left", None)

    assert first["status"] == "queued"


def test_heartbeat_requires_active_job_owner(tmp_data_dir):
    upgrade_head()
    _seed_book()
    job = create("B000CAPTURE", "comic", "left", None)
    claim("windows-1")

    beat = heartbeat(job["id"], "windows-1")

    assert beat["job_id"] == job["id"]
    assert beat["status"] == "claimed"
    assert beat["heartbeat_at"]
    with pytest.raises(ValueError, match="claim"):
        heartbeat(job["id"], "windows-2")

    update_state(
        job["id"],
        "windows-1",
        "failed",
        error_code="kindle_app_exited",
    )
    with pytest.raises(ValueError, match="ジョブ状態"):
        heartbeat(job["id"], "windows-1")


def test_claim_recovers_stale_job_before_claiming_next(
    tmp_data_dir,
    monkeypatch,
):
    upgrade_head()
    _seed_book()
    stale_job = create("B000CAPTURE", "comic", "left", None)
    claim("windows-stale")
    with with_db() as conn:
        conn.execute(
            """
            UPDATE capture_jobs
            SET heartbeat_at='2026-07-25T10:00:00+09:00'
            WHERE id=?
            """,
            (stale_job["id"],),
        )
        conn.execute(
            """
            INSERT INTO books(
                asin,title,title_normalized,category,book_type
            ) VALUES ('B000NEXT','次の作品','次の作品','kindle','comic')
            """
        )
    fixed_now = datetime(2026, 7, 25, 10, 10, tzinfo=JST)
    monkeypatch.setattr(capture_jobs_service, "jst_now", lambda: fixed_now)
    next_job = create("B000NEXT", "comic", "left", None)

    claimed = claim("windows-next")

    assert claimed is not None
    assert claimed["id"] == next_job["id"]
    with with_db() as conn:
        row = conn.execute(
            "SELECT status,error_code,completed_at FROM capture_jobs WHERE id=?",
            (stale_job["id"],),
        ).fetchone()
    assert row["status"] == "failed"
    assert row["error_code"] == "agent_heartbeat_timeout"
    assert row["completed_at"] == "2026-07-25T10:10:00+09:00"
