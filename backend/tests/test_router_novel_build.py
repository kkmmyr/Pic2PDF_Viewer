"""routers/novel_build.py の HTTP レイヤテスト（worker は動かさない）。"""
import pytest

from services.novel_db import with_db
from services.novel_db.migrations import upgrade_head


@pytest.fixture
def db_initialized(tmp_data_dir):
    upgrade_head()
    return tmp_data_dir


# ---------------------------------------------------------------------------
# POST /api/novel/build/enqueue
# ---------------------------------------------------------------------------

def test_enqueue_single_book(client, db_initialized):
    res = client.post("/api/novel/build/enqueue", json={"book_name": "花太郎", "all_books": False})
    assert res.status_code == 200
    body = res.json()
    assert body["job_id"] > 0
    assert body["queued_position"] == 1


def test_enqueue_all_books(client, db_initialized):
    res = client.post("/api/novel/build/enqueue", json={"all_books": True})
    assert res.status_code == 200
    assert res.json()["job_id"] > 0


def test_enqueue_missing_book_name_returns_422(client, db_initialized):
    res = client.post("/api/novel/build/enqueue", json={"all_books": False})
    assert res.status_code == 422


def test_enqueue_duplicate_book_returns_422(client, db_initialized):
    client.post("/api/novel/build/enqueue", json={"book_name": "花太郎", "all_books": False})
    res = client.post("/api/novel/build/enqueue", json={"book_name": "花太郎", "all_books": False})
    assert res.status_code == 422
    assert "already queued or running" in res.json()["detail"]


def test_enqueue_different_books_allowed(client, db_initialized):
    r1 = client.post("/api/novel/build/enqueue", json={"book_name": "花太郎", "all_books": False})
    r2 = client.post("/api/novel/build/enqueue", json={"book_name": "千の刀", "all_books": False})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["queued_position"] == 2


# ---------------------------------------------------------------------------
# GET /api/novel/build/status
# ---------------------------------------------------------------------------

def test_status_empty_queue(client, db_initialized):
    res = client.get("/api/novel/build/status")
    assert res.status_code == 200
    body = res.json()
    assert body["is_running"] is False
    assert body["current_job"] is None
    assert body["queued_jobs"] == []
    assert body["recent_finished"] == []


def test_status_shows_only_full_build_jobs(client, db_initialized):
    # full_build ジョブ
    client.post("/api/novel/build/enqueue", json={"book_name": "花太郎", "all_books": False})
    # rebuild ジョブ（別エンドポイント）
    client.post("/api/novel_db/builds", json={"type": "book", "target_id": "千の刀", "mode": "rebuild"})

    res = client.get("/api/novel/build/status")
    body = res.json()
    assert len(body["queued_jobs"]) == 1
    assert body["queued_jobs"][0]["target_id"] == "花太郎"


def test_status_queued_position_increments(client, db_initialized):
    client.post("/api/novel/build/enqueue", json={"book_name": "A", "all_books": False})
    client.post("/api/novel/build/enqueue", json={"book_name": "B", "all_books": False})

    body = client.get("/api/novel/build/status").json()
    assert len(body["queued_jobs"]) == 2
    targets = [j["target_id"] for j in body["queued_jobs"]]
    assert "A" in targets and "B" in targets


# ---------------------------------------------------------------------------
# DELETE /api/novel/build/jobs/{job_id}
# ---------------------------------------------------------------------------

def test_cancel_queued_job(client, db_initialized):
    enqueue_res = client.post(
        "/api/novel/build/enqueue", json={"book_name": "花太郎", "all_books": False}
    )
    job_id = enqueue_res.json()["job_id"]

    res = client.delete(f"/api/novel/build/jobs/{job_id}")
    assert res.status_code == 204

    body = client.get("/api/novel/build/status").json()
    assert len(body["queued_jobs"]) == 0


def test_cancel_nonexistent_job_returns_404(client, db_initialized):
    res = client.delete("/api/novel/build/jobs/99999")
    assert res.status_code == 404


def test_cancel_running_job_returns_409(client, db_initialized):
    enqueue_res = client.post(
        "/api/novel/build/enqueue", json={"book_name": "花太郎", "all_books": False}
    )
    job_id = enqueue_res.json()["job_id"]

    # 手動で running 状態に更新
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET state='running', started_at=datetime('now') WHERE id=?",
            (job_id,),
        )
        conn.commit()

    res = client.delete(f"/api/novel/build/jobs/{job_id}")
    assert res.status_code == 409
