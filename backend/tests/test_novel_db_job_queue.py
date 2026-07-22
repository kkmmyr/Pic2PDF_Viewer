"""services/novel_db/job_queue.py の単体テスト（worker は起動しない）。"""

from unittest.mock import patch

import pytest

from services.novel_db import with_db
from services.novel_db.job_queue import NovelDbJobQueue
from services.novel_db.migrations import upgrade_head


@pytest.fixture
def queue(tmp_data_dir):
    """schema を初期化した後、worker を起動しない単独 NovelDbJobQueue を返す。"""
    upgrade_head()
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
    assert status["queued_jobs"][0]["mode"] == "rebuild"


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
            "UPDATE rebuild_jobs SET state='running', started_at=datetime('now') WHERE id = ?",
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
    job_id, _ = queue.enqueue("book", "a", mode="ocr")
    status = queue.get_status()
    assert status["queued_jobs"][0]["mode"] == "ocr"


def test_update_detail_writes_to_db(queue):
    """_update_detail が current_detail カラムを更新する。"""
    job_id, _ = queue.enqueue("book", "a")
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET state='running', started_at=datetime('now') WHERE id = ?",
            (job_id,),
        )
        conn.commit()

    queue._worker._update_detail(job_id, "embedding 10/100 チャンク")

    with with_db() as conn:
        row = conn.execute("SELECT current_detail FROM rebuild_jobs WHERE id = ?", (job_id,)).fetchone()
    assert row is not None
    assert row[0] == "embedding 10/100 チャンク"


def test_get_status_current_job_includes_current_detail(queue):
    """get_status の current_job に current_detail が含まれる。"""
    job_id, _ = queue.enqueue("book", "b")
    with with_db() as conn:
        conn.execute(
            "UPDATE rebuild_jobs SET state='running', started_at=datetime('now'), "
            "current_detail='コンテキスト 5/50 チャンク' WHERE id = ?",
            (job_id,),
        )
        conn.commit()

    status = queue.get_status()
    assert status["is_running"] is True
    assert status["current_job"]["current_detail"] == "コンテキスト 5/50 チャンク"


def test_update_detail_overwrites_previous_value(queue):
    """_update_detail を複数回呼ぶと最新値に上書きされる。"""
    job_id, _ = queue.enqueue("book", "c")
    queue._worker._update_detail(job_id, "first")
    queue._worker._update_detail(job_id, "second")

    with with_db() as conn:
        row = conn.execute("SELECT current_detail FROM rebuild_jobs WHERE id = ?", (job_id,)).fetchone()
    assert row[0] == "second"


def test_generate_relations_loads_series_index_once(queue):
    """複数書籍の関係生成でもnovelメタは1回だけ索引化する。"""
    worker = queue._worker
    job = {
        "id": 1,
        "job_type": "all",
        "target_id": None,
        "mode": "generate_relations",
    }

    with (
        patch.object(worker, "_resolve_targets", return_value=["book-a", "book-b"]),
        patch.object(worker, "_update_progress"),
        patch(
            "services.novel_db.job_worker.load_book_series_ids",
            return_value={"book-a": "series-1", "book-b": "series-1"},
        ) as mock_load_index,
        patch("services.novel_db.job_worker.generate_book_relations") as mock_generate,
    ):
        worker._execute_job(job)

    mock_load_index.assert_called_once_with()
    assert mock_generate.call_count == 2


def test_ocr_combines_pending_pages_and_publishes_each_book(queue):
    """複数冊でもworkerは1回だけ起動し、ページ保存後に冊単位で確定する。"""
    worker = queue._worker
    job = {"id": 1, "job_type": "all", "target_id": None, "mode": "ocr"}
    input_a = [object()]
    input_b = [object()]
    task_a = {"book_name": "book-a", "page_no": 1, "image_path": "a.png"}
    task_b = {"book_name": "book-b", "page_no": 1, "image_path": "b.png"}
    page_a = {"page_no": 1}
    page_b = {"page_no": 1}

    with (
        patch.object(worker, "_resolve_targets", return_value=["book-a", "book-b"]),
        patch.object(worker, "_update_progress"),
        patch.object(worker, "_update_detail"),
        patch("services.novel_db.job_worker.collect_input_pages", side_effect=[input_a, input_b]),
        patch(
            "services.novel_db.job_worker.prepare_run",
            side_effect=[(11, [task_a]), (12, [task_b])],
        ),
        patch(
            "services.novel_db.job_worker.iter_ocr_pages",
            return_value=iter([("book-a", page_a), ("book-b", page_b)]),
        ) as mock_iter,
        patch("services.novel_db.job_worker.save_page_result") as mock_save,
        patch("services.novel_db.job_worker.publish_run") as mock_publish,
    ):
        worker._execute_job(job)

    mock_iter.assert_called_once_with([task_a, task_b])
    assert mock_save.call_args_list[0].args == (11, page_a)
    assert mock_save.call_args_list[1].args == (12, page_b)
    assert mock_publish.call_args_list[0].args == (11, input_a)
    assert mock_publish.call_args_list[1].args == (12, input_b)
