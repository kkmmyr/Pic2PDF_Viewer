"""services.generate_service の非同期Task寿命を検証する。"""

import asyncio
from unittest.mock import MagicMock

from services import generate_service
from services.job_manager import GenerateJob


async def test_run_generate_job_async_uses_to_thread(monkeypatch):
    job = GenerateJob("test-job", trigger="manual")
    mock_to_thread = MagicMock()

    async def _to_thread(func, *args):
        mock_to_thread(func, *args)

    monkeypatch.setattr(asyncio, "to_thread", _to_thread)

    await generate_service._run_generate_job_async(job)

    mock_to_thread.assert_called_once_with(generate_service._run_generate_job, job)


async def test_start_generate_job_keeps_task_until_completion(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def _run(_job):
        started.set()
        await release.wait()

    monkeypatch.setattr(generate_service, "_run_generate_job_async", _run)

    job = await generate_service.start_generate_job()
    assert job is not None
    await started.wait()

    tasks = list(generate_service._background_tasks)
    assert len(tasks) == 1
    assert tasks[0].get_name() == f"generate-{job.job_id}"

    release.set()
    await asyncio.gather(*tasks)
    await asyncio.sleep(0)

    assert generate_service._background_tasks == set()
    assert generate_service.get_active_job_id() is None
    assert not generate_service.generate_lock.locked()
