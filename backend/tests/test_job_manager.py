"""
services.job_manager のユニットテスト。

実行方法:
    cd backend
    uv run pytest tests/test_job_manager.py -v
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.job_manager import JobStore, JobStatus


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
        j3 = store.create()
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
        assert d["error"] is None

    def test_to_dict_on_failure(self):
        store = JobStore()
        job = store.create()
        job.update(status=JobStatus.FAILED, error="変換失敗")
        d = job.to_dict()
        assert d["status"] == "failed"
        assert d["error"] == "変換失敗"
