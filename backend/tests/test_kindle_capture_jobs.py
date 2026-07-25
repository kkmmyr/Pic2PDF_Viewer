"""Kindle キャプチャジョブと Linux inbox 取込テスト。"""

import hashlib
import json
from pathlib import Path

import config
from services.kindle_catalog.capture_jobs import claim, complete, create, update_state
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.migrations import upgrade_head
from services.meta_store import load_meta


def _seed_book() -> None:
    with with_db() as conn:
        conn.execute(
            "INSERT INTO books(asin,title,title_normalized,category,book_type) "
            "VALUES ('B000CAPTURE','キャプチャ作品','キャプチャ作品','kindle','comic')"
        )


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
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    (ready / "manifest.json").write_text(
        json.dumps(
            {
                "job_id": job["id"],
                "asin": "B000CAPTURE",
                "source": "comic",
                "files": [{"name": "001.png", "sha256": digest}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    update_state(job["id"], "windows-1", "awaiting_files", captured_screens=1)

    result = complete(job["id"], "windows-1")

    assert result["status"] == "succeeded"
    assert Path(tmp_data_dir["COMIC_IMAGES_DIR"], "キャプチャ作品", "001.png").is_file()
    assert load_meta("comic")["キャプチャ作品.pdf"]["asin"] == "B000CAPTURE"
    assert Path(inbox, "processed", job["id"], "manifest.json").is_file()


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
    (ready / "manifest.json").write_text(
        json.dumps(
            {
                "job_id": job["id"],
                "asin": "B000CAPTURE",
                "source": "comic",
                "files": [{"name": "../001.png"}],
            }
        ),
        encoding="utf-8",
    )

    try:
        complete(job["id"], "windows-1")
    except ValueError as exc:
        assert "ファイル名" in str(exc)
    else:
        raise AssertionError("path traversal must be rejected")
