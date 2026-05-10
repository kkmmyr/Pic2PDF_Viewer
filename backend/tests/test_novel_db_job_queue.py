"""services/novel_db/job_queue.py の単体テスト（worker は起動しない）。"""
import pytest

from services.novel_db import init_schema, with_db
from services.novel_db.job_queue import NovelDbJobQueue


@pytest.fixture
def queue(tmp_data_dir):
    """schema を初期化した後、worker を起動しない単独 NovelDbJobQueue を返す。"""
    with with_db() as conn:
        init_schema(conn)
    # 新規インスタンスで状態をクリーンに保つ
    return NovelDbJobQueue()


def test_enqueue_creates_queued_job(queue):
    job_id, position = queue.enqueue("book", "おこぼれ姫 1")
    assert job_id > 0
    assert position == 1

    status = queue.get_status()
    assert status["is_running"] is False
    assert len(status["queued_jobs"]) == 1
    assert status["queued_jobs"][0]["id"] == job_id
    assert status["queued_jobs"][0]["type"] == "book"
    assert status["queued_jobs"][0]["target_id"] == "おこぼれ姫 1"
    assert status["queued_jobs"][0]["mode"] == "pdf_text"


def test_enqueue_returns_correct_queue_position(queue):
    j1, p1 = queue.enqueue("book", "a")
    j2, p2 = queue.enqueue("book", "b")
    j3, p3 = queue.enqueue("all")
    assert (p1, p2, p3) == (1, 2, 3)
    assert (j1, j2, j3) == (j1, j2, j3)
    assert j1 < j2 < j3


def test_cancel_queued_job(queue):
    job_id, _ = queue.enqueue("book", "a")
    result = queue.cancel(job_id)
    assert result == "canceled"

    status = queue.get_status()
    assert len(status["queued_jobs"]) == 0
    finished = status["recent_finished"]
    assert len(finished) == 1
    assert finished[0]["id"] == job_id
    assert finished[0]["state"] == "canceled"


def test_cancel_returns_not_found_for_unknown_id(queue):
    assert queue.cancel(99999) == "not_found"


def test_cancel_returns_running_for_running_job(queue):
    """state='running' のジョブは "running" を返す（実装メモ: cancel 不可シグナル）。"""
    # ジョブを INSERT してから手動で running 状態にする
    job_id, _ = queue.enqueue("book", "a")
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET state='running', started_at=datetime('now') "
            "WHERE id = ?",
            (job_id,),
        )
        conn.commit()

    result = queue.cancel(job_id)
    assert result == "running"


def test_get_status_includes_recent_finished(queue):
    """完了済みジョブは recent_finished に含まれる（最大 5 件）。"""
    for i in range(7):
        job_id, _ = queue.enqueue("book", f"book-{i}")
        with with_db() as conn:
            conn.execute(
                "UPDATE rebuild_jobs SET state='completed', "
                "started_at=datetime('now'), finished_at=datetime('now') "
                "WHERE id = ?",
                (job_id,),
            )
            conn.commit()

    status = queue.get_status()
    assert len(status["recent_finished"]) == 5
    assert all(j["state"] == "completed" for j in status["recent_finished"])


def test_enqueue_with_explicit_mode(queue):
    job_id, _ = queue.enqueue("book", "a", mode="reocr")
    status = queue.get_status()
    assert status["queued_jobs"][0]["mode"] == "reocr"
