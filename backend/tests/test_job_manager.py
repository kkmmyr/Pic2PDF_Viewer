"""
services.job_manager のユニットテスト。

実行方法:
    cd backend
    uv run pytest tests/test_job_manager.py -v
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.job_manager import GenerateJob, JobStatus, JobStore


class TestJobStoreGetActiveCurrentItem:
    def test_empty_store_returns_none(self):
        store = JobStore()
        assert store.get_active_current_item() is None

    def test_pending_job_returns_none(self):
        store = JobStore()
        job = store.create()
        assert job.status == JobStatus.PENDING
        assert store.get_active_current_item() is None

    def test_completed_job_returns_none(self):
        store = JobStore()
        job = store.create()
        job.update(status=JobStatus.COMPLETED)
        assert store.get_active_current_item() is None

    def test_failed_job_returns_none(self):
        store = JobStore()
        job = store.create()
        job.update(status=JobStatus.FAILED, error="something went wrong")
        assert store.get_active_current_item() is None

    def test_running_job_returns_current_item(self):
        store = JobStore()
        job = store.create()
        job.update(status=JobStatus.RUNNING, current_item="vol01.pdf")
        assert store.get_active_current_item() == "vol01.pdf"

    def test_running_job_with_none_current_item(self):
        store = JobStore()
        job = store.create()
        job.update(status=JobStatus.RUNNING)
        assert store.get_active_current_item() is None

    def test_newest_running_job_wins(self):
        """複数の RUNNING ジョブがある場合、最新（_order 末尾）のものが返る。"""
        store = JobStore()
        job1 = store.create()
        job1.update(status=JobStatus.RUNNING, current_item="old.pdf")
        job2 = store.create()
        job2.update(status=JobStatus.RUNNING, current_item="new.pdf")
        assert store.get_active_current_item() == "new.pdf"

    def test_running_then_completed_returns_none(self):
        store = JobStore()
        job = store.create()
        job.update(status=JobStatus.RUNNING, current_item="vol01.pdf")
        assert store.get_active_current_item() == "vol01.pdf"
        job.update(status=JobStatus.COMPLETED, current_item=None)
        assert store.get_active_current_item() is None

    def test_mixed_states_returns_running(self):
        """COMPLETED / RUNNING / PENDING が混在しても RUNNING のものを返す。"""
        store = JobStore()
        j_completed = store.create()
        j_completed.update(status=JobStatus.COMPLETED)
        j_running = store.create()
        j_running.update(status=JobStatus.RUNNING, current_item="target.pdf")
        _j_pending = store.create()  # PENDING のまま
        assert store.get_active_current_item() == "target.pdf"


class TestJobStoreCreate:
    def test_create_returns_job_with_uuid(self):
        store = JobStore()
        job = store.create()
        assert len(job.job_id) == 36  # UUID4 形式

    def test_initial_status_is_pending(self):
        store = JobStore()
        job = store.create()
        assert job.status == JobStatus.PENDING
        assert job.current_item is None
        assert job.files == []
        assert job.error is None

    def test_get_returns_created_job(self):
        store = JobStore()
        job = store.create()
        assert store.get(job.job_id) is job

    def test_get_unknown_id_returns_none(self):
        store = JobStore()
        assert store.get("nonexistent-id") is None

    def test_evicts_oldest_when_over_max(self):
        """MAX_JOBS を超えたら最古のジョブが押し出される。"""
        store = JobStore()
        store._MAX_JOBS = 3
        j1 = store.create()
        j2 = store.create()
        store.create()
        j4 = store.create()  # j1 が押し出される
        assert store.get(j1.job_id) is None
        assert store.get(j2.job_id) is j2
        assert store.get(j4.job_id) is j4

    def test_evicted_job_not_returned_by_get_active(self):
        """RUNNING 中に押し出されたジョブは get_active_current_item の対象外になる。"""
        store = JobStore()
        store._MAX_JOBS = 2
        j1 = store.create()
        j1.update(status=JobStatus.RUNNING, current_item="old.pdf")
        store.create()
        store.create()  # j1 が押し出される
        assert store.get_active_current_item() is None


class TestGenerateJobUpdate:
    def test_update_sets_fields(self):
        store = JobStore()
        job = store.create()
        job.update(status=JobStatus.RUNNING, current_item="file.pdf", message="処理中")
        assert job.status == JobStatus.RUNNING
        assert job.current_item == "file.pdf"
        assert job.message == "処理中"

    def test_to_dict_structure(self):
        store = JobStore()
        job = store.create()
        job.update(status=JobStatus.RUNNING, current_item="a.pdf", message="処理中", files=["a.pdf"])
        d = job.to_dict()
        assert d["status"] == "running"
        assert d["current_item"] == "a.pdf"
        assert d["message"] == "処理中"
        assert d["files"] == ["a.pdf"]
        assert d["failed_items"] == []
        assert d["error"] is None

    def test_to_dict_includes_failed_items(self):
        """サイレント失敗を防ぐため、書籍単位の失敗が to_dict に含まれる。"""
        store = JobStore()
        job = store.create()
        failed = [{"name": "broken", "error": "ZIP 展開エラー"}]
        job.update(status=JobStatus.COMPLETED, files=["good.pdf"], failed_items=failed)
        d = job.to_dict()
        assert d["files"] == ["good.pdf"]
        assert d["failed_items"] == failed

    def test_to_dict_on_failure(self):
        store = JobStore()
        job = store.create()
        job.update(status=JobStatus.FAILED, error="変換失敗")
        d = job.to_dict()
        assert d["status"] == "failed"
        assert d["error"] == "変換失敗"


# ---------------------------------------------------------------------------
# 並行性テスト
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_creates_produce_unique_ids(self):
        """100 件並行 create で全件異なる UUID が振られ、最大件数まで保持される。"""
        store = JobStore()
        store._MAX_JOBS = 1000
        jobs: list[GenerateJob] = []
        lock = threading.Lock()

        def _create_one():
            j = store.create()
            with lock:
                jobs.append(j)

        threads = [threading.Thread(target=_create_one) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ids = {j.job_id for j in jobs}
        assert len(ids) == 100  # 全件 UUID がユニーク

    def test_concurrent_updates_no_corruption(self):
        """同一ジョブを並行 update してもフィールドが破壊されない。"""
        store = JobStore()
        job = store.create()

        def _set_running():
            job.update(status=JobStatus.RUNNING, current_item="x.pdf")

        def _set_completed():
            job.update(status=JobStatus.COMPLETED, files=["x.pdf"])

        threads = [threading.Thread(target=_set_running) for _ in range(20)] + [
            threading.Thread(target=_set_completed) for _ in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 最後の update がどちらかの状態になっていればOK（lock があれば壊れない）
        assert job.status in (JobStatus.RUNNING, JobStatus.COMPLETED)

    def test_eviction_boundary_n_plus_1(self):
        """N+1 件目の create で先頭 1 件が確実に evict される。"""
        store = JobStore()
        store._MAX_JOBS = 5
        jobs = [store.create() for _ in range(5)]

        # 5 件すべて取得可能
        for j in jobs:
            assert store.get(j.job_id) is j

        # 6 件目で先頭が消える
        store.create()
        assert store.get(jobs[0].job_id) is None
        # 残り 4 件は残っている
        for j in jobs[1:]:
            assert store.get(j.job_id) is j

    def test_eviction_concurrent(self):
        """並行 create 時も MAX_JOBS を超えない。"""
        store = JobStore()
        store._MAX_JOBS = 10

        def _create():
            for _ in range(5):
                store.create()

        threads = [threading.Thread(target=_create) for _ in range(10)]  # 50 件
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # _order と _jobs の長さは MAX_JOBS 以下
        assert len(store._order) <= store._MAX_JOBS
        assert len(store._jobs) <= store._MAX_JOBS
