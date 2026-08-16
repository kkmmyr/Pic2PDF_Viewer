"""Kindle capture publication rollback and compensation tests."""

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

import config
from services.kindle_catalog import capture_registration
from services.kindle_catalog.capture_jobs import (
    claim,
    complete,
    create,
    update_state,
)
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.migrations import upgrade_head
from services.meta_store import load_meta, update_meta_locked


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


@pytest.mark.parametrize(
    "failure_point",
    [
        "after_ready_validation",
        "after_staging_copy",
        "after_existing_backup",
        "after_target_publish",
        "after_meta_update",
        "after_package_archive",
        "before_job_update",
    ],
)
@pytest.mark.parametrize("replacing_existing", [False, True])
def test_complete_rolls_back_each_publish_boundary(
    failure_point,
    replacing_existing,
    tmp_data_dir,
    tmp_path,
    monkeypatch,
    make_png,
):
    inbox = tmp_path / "capture-inbox"
    monkeypatch.setattr(config, "KINDLE_CAPTURE_INBOX_DIR", str(inbox))
    job = _prepare_ready_job(inbox, make_png)
    target = Path(tmp_data_dir["COMIC_IMAGES_DIR"], "キャプチャ作品")
    if replacing_existing:
        target.mkdir(parents=True)
        (target / "001.png").write_bytes(b"old-image")

        def seed_meta(data):
            data["キャプチャ作品.pdf"] = {
                "authors": ["既存著者"],
                "asin": "B000CAPTURE",
                "read_state": "reading",
            }

        update_meta_locked("comic", seed_meta)
    elif failure_point == "after_existing_backup":
        pytest.skip("既存画像の退避地点は置換時だけ通過する")

    def fail_at(point: str) -> None:
        if point == failure_point:
            raise RuntimeError(f"injected: {point}")

    monkeypatch.setattr(capture_registration, "_inject_failure", fail_at)

    with pytest.raises(RuntimeError, match=failure_point):
        complete(job["id"], "windows-1")

    if replacing_existing:
        assert (target / "001.png").read_bytes() == b"old-image"
        meta = load_meta("comic")["キャプチャ作品.pdf"]
        assert meta["asin"] == "B000CAPTURE"
        assert meta["authors"] == ["既存著者"]
        assert meta["read_state"] == "reading"
    else:
        assert not target.exists()
        assert "キャプチャ作品.pdf" not in load_meta("comic")
    assert Path(inbox, f"{job['id']}.ready", "manifest.json").is_file()
    assert not Path(inbox, "processed", job["id"]).exists()
    assert not Path(target.parent, f".{job['id']}.partial").exists()
    with with_db() as conn:
        row = conn.execute(
            "SELECT status,book_id FROM capture_jobs WHERE id=?",
            (job["id"],),
        ).fetchone()
    assert row["status"] == "awaiting_files"
    assert row["book_id"] is None


def test_complete_compensates_when_conditional_job_update_matches_zero_rows(
    tmp_data_dir,
    tmp_path,
    monkeypatch,
    make_png,
):
    inbox = tmp_path / "capture-inbox"
    monkeypatch.setattr(config, "KINDLE_CAPTURE_INBOX_DIR", str(inbox))
    job = _prepare_ready_job(inbox, make_png)
    target = Path(tmp_data_dir["COMIC_IMAGES_DIR"], "キャプチャ作品")

    def change_job_before_update(point: str) -> None:
        if point != "before_job_update":
            return
        with with_db() as conn:
            conn.execute(
                "UPDATE capture_jobs SET status='failed' WHERE id=?",
                (job["id"],),
            )

    monkeypatch.setattr(
        capture_registration,
        "_inject_failure",
        change_job_before_update,
    )

    with pytest.raises(ValueError, match="完了更新に失敗"):
        complete(job["id"], "windows-1")

    assert not target.exists()
    assert "キャプチャ作品.pdf" not in load_meta("comic")
    assert Path(inbox, f"{job['id']}.ready", "manifest.json").is_file()
    assert not Path(inbox, "processed", job["id"]).exists()
    assert not Path(target.parent, f".{job['id']}.partial").exists()
    with with_db() as conn:
        row = conn.execute(
            "SELECT status,book_id FROM capture_jobs WHERE id=?",
            (job["id"],),
        ).fetchone()
    assert row["status"] == "failed"
    assert row["book_id"] is None
