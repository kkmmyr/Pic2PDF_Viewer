"""routers/novel_db.py の HTTP レイヤテスト（worker は動かさない）。"""

from pathlib import Path

import pytest

from services.novel_db import with_db
from services.novel_db.migrations import upgrade_head


@pytest.fixture
def db_initialized(tmp_data_dir):
    upgrade_head()
    return tmp_data_dir


def _put_image_dir(tmp_data_dir, name: str) -> None:
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"])
    (images_dir / name).mkdir(parents=True, exist_ok=True)


def test_get_books_returns_unindexed_book_list(client, db_initialized):
    _put_image_dir(db_initialized, "book-1")
    _put_image_dir(db_initialized, "book-2")

    res = client.get("/api/novel_db/books")
    assert res.status_code == 200
    body = res.json()
    assert {b["name"] for b in body} == {"book-1", "book-2"}
    assert all(b["is_indexed"] is False for b in body)
    assert all("thumbnail_url" in b for b in body)


def test_get_series_empty_when_no_series_assigned(client, db_initialized):
    _put_image_dir(db_initialized, "book-1")
    res = client.get("/api/novel_db/series")
    assert res.status_code == 200
    assert res.json() == []


def test_post_rebuild_book_enqueues_and_returns_job_id(client, db_initialized):
    res = client.post(
        "/api/novel_db/builds",
        json={"type": "book", "target_id": "book-1"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["job_id"] > 0
    assert body["queued_position"] == 1


def test_post_rebuild_all_does_not_require_target_id(client, db_initialized):
    res = client.post("/api/novel_db/builds", json={"type": "all"})
    assert res.status_code == 200
    assert res.json()["job_id"] > 0


def test_post_rebuild_book_requires_target_id(client, db_initialized):
    res = client.post("/api/novel_db/builds", json={"type": "book"})
    assert res.status_code == 422
    assert "target_id" in res.json()["detail"].lower()


@pytest.mark.parametrize("target_id", ["../outside", "C:/Windows", "folder/book"])
def test_post_rebuild_book_rejects_unsafe_target(client, db_initialized, target_id):
    res = client.post(
        "/api/novel_db/builds",
        json={"type": "book", "target_id": target_id, "mode": "ocr"},
    )
    assert res.status_code == 400


def test_post_rebuild_series_requires_target_id(client, db_initialized):
    res = client.post("/api/novel_db/builds", json={"type": "series"})
    assert res.status_code == 422


def test_post_rebuild_accepts_ocr_mode(client, db_initialized):
    """mode='ocr' はキューに登録されること（§4.2）。"""
    res = client.post(
        "/api/novel_db/builds",
        json={"type": "book", "target_id": "book-1", "mode": "ocr"},
    )
    assert res.status_code == 200
    assert "job_id" in res.json()


def test_post_rebuild_rejects_invalid_type(client, db_initialized):
    res = client.post(
        "/api/novel_db/builds",
        json={"type": "invalid", "target_id": "x"},
    )
    assert res.status_code == 422


def test_get_rebuild_status_returns_empty_initially(client, db_initialized):
    res = client.get("/api/novel_db/builds/status")
    assert res.status_code == 200
    body = res.json()
    assert body["is_running"] is False
    assert body["current_job"] is None
    assert body["queued_jobs"] == []
    assert body["recent_finished"] == []


def test_get_rebuild_status_after_enqueue(client, db_initialized):
    enq = client.post(
        "/api/novel_db/builds",
        json={"type": "book", "target_id": "book-1"},
    )
    job_id = enq.json()["job_id"]

    res = client.get("/api/novel_db/builds/status")
    assert res.status_code == 200
    body = res.json()
    assert body["is_running"] is False
    assert len(body["queued_jobs"]) == 1
    assert body["queued_jobs"][0]["id"] == job_id


def test_delete_rebuild_cancels_queued_job(client, db_initialized):
    enq = client.post(
        "/api/novel_db/builds",
        json={"type": "book", "target_id": "book-1"},
    )
    job_id = enq.json()["job_id"]

    res = client.delete(f"/api/novel_db/builds/{job_id}")
    assert res.status_code == 204

    status = client.get("/api/novel_db/builds/status").json()
    assert status["queued_jobs"] == []


def test_delete_rebuild_returns_404_for_unknown_id(client, db_initialized):
    res = client.delete("/api/novel_db/builds/99999")
    assert res.status_code == 404


def test_delete_rebuild_returns_409_for_running_job(client, db_initialized):
    enq = client.post(
        "/api/novel_db/builds",
        json={"type": "book", "target_id": "book-1"},
    )
    job_id = enq.json()["job_id"]

    # 手動で running に
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET state='running', started_at=datetime('now') WHERE id = ?",
            (job_id,),
        )
        conn.commit()

    res = client.delete(f"/api/novel_db/builds/{job_id}")
    assert res.status_code == 409
