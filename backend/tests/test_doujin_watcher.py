"""
services.doujin_watcher.DoujinWatcher のユニットテスト。

`tick()` は sleep を含まない同期的に呼べる async メソッドなので、直接呼んで
状態遷移を検証する。`scan_and_generate` は重い処理なのでモック化する。

実行方法:
    cd backend
    uv run pytest tests/test_doujin_watcher.py -v
"""

import asyncio
import os
import time

from services.doujin_watcher import DoujinWatcher
from services.generate_service import get_active_job_id, job_store
from services.job_manager import JobStatus
from services.pdf_generator import GenerateResult


async def _wait_job_done(job_id: str, timeout: float = 10.0):
    # 同期 time.sleep はイベントループを塞ぎ、start_generate_job が
    # create_task したジョブ本体が永遠に走らない。必ず await で譲る。
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = job_store.get(job_id)
        if job is not None and job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


class TestTickWaitingStable:
    async def test_changing_snapshot_stays_waiting_stable_and_does_not_start_job(self, tmp_data_dir):
        input_dir = tmp_data_dir["DOUJIN_INPUT_DIR"]
        watcher = DoujinWatcher()

        os.makedirs(os.path.join(input_dir, "alpha"), exist_ok=True)
        with open(os.path.join(input_dir, "alpha", "1.webp"), "wb") as f:
            f.write(b"a")
        await watcher.tick()
        assert watcher.state == "waiting_stable"
        assert get_active_job_id() is None

        # コピー進行中を模して内容を変更 → 依然 waiting_stable のまま
        with open(os.path.join(input_dir, "alpha", "2.webp"), "wb") as f:
            f.write(b"b")
        await watcher.tick()
        assert watcher.state == "waiting_stable"
        assert get_active_job_id() is None


class TestTickStableStartsJob:
    async def test_stable_snapshot_twice_starts_generation_job(self, tmp_data_dir, monkeypatch):
        input_dir = tmp_data_dir["DOUJIN_INPUT_DIR"]
        watcher = DoujinWatcher()

        monkeypatch.setattr(
            "services.generate_service.scan_and_generate",
            lambda *a, **kw: GenerateResult(generated=["book.pdf"], failed_items=[]),
        )

        os.makedirs(os.path.join(input_dir, "beta"), exist_ok=True)
        with open(os.path.join(input_dir, "beta", "1.webp"), "wb") as f:
            f.write(b"a")

        await watcher.tick()  # 1回目: waiting_stable
        assert watcher.state == "waiting_stable"

        await watcher.tick()  # 2回目: スナップショット不変 → ジョブ起動
        assert watcher.state == "running"
        job_id = get_active_job_id()
        assert job_id is not None

        job = await _wait_job_done(job_id)
        assert job.status == JobStatus.COMPLETED
        assert job.trigger == "auto"
        assert watcher.last_auto_job is not None
        assert watcher.last_auto_job["job_id"] == job_id
        assert watcher.last_auto_job["status"] == "completed"


class TestTickFailedRemnant:
    async def test_failed_snapshot_remnant_blocks_auto_retry(self, tmp_data_dir, monkeypatch):
        input_dir = tmp_data_dir["DOUJIN_INPUT_DIR"]
        watcher = DoujinWatcher()

        def _boom(*a, **kw):
            raise RuntimeError("corrupt zip")

        monkeypatch.setattr("services.generate_service.scan_and_generate", _boom)

        with open(os.path.join(input_dir, "bad.zip"), "wb") as f:
            f.write(b"not a real zip")

        await watcher.tick()  # waiting_stable
        await watcher.tick()  # 起動 → running
        job_id = get_active_job_id()
        assert job_id is not None
        job = await _wait_job_done(job_id)
        assert job.status == JobStatus.FAILED

        # 同じ残骸に対する3回目: 自動再試行しない
        await watcher.tick()
        assert watcher.state == "idle"
        assert watcher.retry_blocked is True
        assert get_active_job_id() is None


class TestTickIdleAndMissing:
    async def test_empty_directory_is_idle_and_clears_last_attempted(self, tmp_data_dir):
        watcher = DoujinWatcher()
        watcher._last_attempted = frozenset({("stale", "zip", 1, 1.0)})

        await watcher.tick()

        assert watcher.state == "idle"
        assert watcher.retry_blocked is False
        assert watcher.pending_items == []
        assert watcher._last_attempted is None

    async def test_input_dir_missing_sets_state_without_raising(self, tmp_data_dir, monkeypatch):
        import config

        monkeypatch.setattr(config, "DOUJIN_INPUT_DIR", "/nope/does/not/exist/qwerty")
        watcher = DoujinWatcher()

        await watcher.tick()

        assert watcher.state == "input_missing"


class TestPendingItems:
    async def test_pending_items_include_zip_and_folder_entries(self, tmp_data_dir):
        input_dir = tmp_data_dir["DOUJIN_INPUT_DIR"]
        watcher = DoujinWatcher()

        with open(os.path.join(input_dir, "book.zip"), "wb") as f:
            f.write(b"x")
        os.makedirs(os.path.join(input_dir, "folder_book"), exist_ok=True)
        with open(os.path.join(input_dir, "folder_book", "1.webp"), "wb") as f:
            f.write(b"x")
        # その他形式は無視される
        with open(os.path.join(input_dir, "readme.txt"), "wb") as f:
            f.write(b"x")

        await watcher.tick()

        names_kinds = {(p.name, p.kind) for p in watcher.pending_items}
        assert names_kinds == {("book.zip", "zip"), ("folder_book", "folder")}
