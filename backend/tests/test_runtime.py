"""Exercise cleanup failures and cancellation without starting real resources."""

import asyncio
from collections.abc import Callable
from dataclasses import replace

import pytest

from bootstrap.runtime import RuntimeResources, manage_runtime
from tests.test_main_lifespan import RecordingService


def make_resources(record: Callable[[str], None]) -> RuntimeResources:
    return RuntimeResources(
        initialize_meta=lambda: record("meta"),
        migrate_novel=lambda: record("novel"),
        migrate_kindle=lambda: record("kindle"),
        job_queue=RecordingService("queue", record),
        doujin_watcher=RecordingService("watcher", record),
    )


async def test_runtime_sessions_do_not_share_resources() -> None:
    first: list[str] = []
    second: list[str] = []

    def resources(events: list[str]) -> RuntimeResources:
        return RuntimeResources(
            initialize_meta=lambda: events.append("meta"),
            migrate_novel=lambda: events.append("novel"),
            migrate_kindle=lambda: events.append("kindle"),
            job_queue=RecordingService("queue", events.append),
            doujin_watcher=RecordingService("watcher", events.append),
        )

    async with manage_runtime(resources(first)):
        first.append("serve")
        async with manage_runtime(resources(second)):
            second.append("serve")
        assert first == ["meta", "novel", "kindle", "queue.start", "watcher.start", "serve"]
        assert second == [*first, "watcher.stop", "queue.stop"]
    assert first == second


@pytest.mark.parametrize("phase", ["watcher.start", "serve", "watcher.stop"])
async def test_all_failures_keep_identity_and_cleanup_order(phase: str) -> None:
    events: list[str] = []
    original = RuntimeError(phase)
    queue_error = OSError("queue stop failed")
    watcher_error = ValueError("watcher stop failed")

    def record(step: str) -> None:
        events.append(step)
        if step == phase:
            raise original
        if step == "watcher.stop":
            raise watcher_error
        if step == "queue.stop":
            raise queue_error

    with pytest.raises(ExceptionGroup) as caught:
        async with manage_runtime(make_resources(record)):
            record("serve")
    expected = [original, watcher_error, queue_error] if phase == "serve" else [original, queue_error]
    assert list(caught.value.exceptions) == expected
    assert events[-1] == "queue.stop"
    if phase == "watcher.start":
        assert "watcher.stop" not in events
    assert queue_error.__notes__ == ["Runtime resource stop failed: queue"]


@pytest.mark.parametrize("error", [RuntimeError("serving"), TimeoutError("caller deadline")])
async def test_original_exception_is_preserved_without_cleanup_failure(error: Exception) -> None:
    events: list[str] = []
    with pytest.raises(type(error)) as caught:
        async with manage_runtime(make_resources(events.append)):
            raise error
    assert caught.value is error
    assert events[-2:] == ["watcher.stop", "queue.stop"]


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_invalid_stop_timeout_is_rejected_before_initialization(timeout: float) -> None:
    events: list[str] = []
    with pytest.raises(ValueError, match="finite and positive"):
        replace(make_resources(events.append), stop_timeout=timeout)
    assert events == []


async def test_stop_timeout_continues_cleanup_without_leaving_a_task() -> None:
    events: list[str] = []
    stopped = asyncio.Event()

    class WaitingService(RecordingService):
        async def stop(self) -> None:
            self.record("watcher.stop")
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    resources = replace(
        make_resources(events.append),
        doujin_watcher=WaitingService("watcher", events.append),
        stop_timeout=0.01,
    )
    before = asyncio.all_tasks()
    with pytest.raises(TimeoutError) as caught:
        async with manage_runtime(resources):
            pass
    assert caught.value.__notes__ == ["Runtime resource stop failed: watcher"]
    assert stopped.is_set()
    assert events[-2:] == ["watcher.stop", "queue.stop"]
    assert asyncio.all_tasks() == before


@pytest.mark.parametrize(
    ("phase", "expected_stops"),
    [
        ("queue.start", []),
        ("watcher.start", ["queue.stop"]),
        ("serve", ["watcher.stop", "queue.stop"]),
        ("watcher.stop", ["watcher.stop", "queue.stop"]),
    ],
)
@pytest.mark.parametrize("stop_fails", [False, True])
async def test_owner_cancellation_preserves_task_state_and_cleans_started_resources(
    phase: str, expected_stops: list[str], stop_fails: bool
) -> None:
    events: list[str] = []
    reached = asyncio.Event()
    cleanup_reached = asyncio.Event()
    release_cleanup = asyncio.Event()
    stop_error = OSError("queue stop failed")

    class GatedService(RecordingService):
        async def start(self) -> None:
            await super().start()
            if phase == f"{self.name}.start":
                reached.set()
                await asyncio.Event().wait()

        async def stop(self) -> None:
            await super().stop()
            cleanup_reached.set()
            if phase == f"{self.name}.stop":
                reached.set()
            await release_cleanup.wait()
            if stop_fails and self.name == "queue":
                raise stop_error

    resources = replace(
        make_resources(events.append),
        job_queue=GatedService("queue", events.append),
        doujin_watcher=GatedService("watcher", events.append),
    )

    async def run() -> None:
        async with manage_runtime(resources):
            events.append("serve")
            if phase == "serve":
                reached.set()
                await asyncio.Event().wait()

    before = asyncio.all_tasks()
    task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(reached.wait(), timeout=2)
        task.cancel("first cancellation")
        if phase != "queue.start":
            await asyncio.wait_for(cleanup_reached.wait(), timeout=2)
            await asyncio.sleep(0)
            task.cancel("second cancellation")
            await asyncio.sleep(0)
            assert not task.done()
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError) as caught:
            await asyncio.wait_for(task, timeout=2)
        assert str(caught.value) == "first cancellation"
        assert task.cancelled()
        stops = [event for event in events if event.endswith(".stop")]
        assert stops == expected_stops
        if stop_fails and phase != "queue.start":
            assert isinstance(caught.value.__cause__, ExceptionGroup)
            assert caught.value.__cause__.exceptions == (stop_error,)
        assert asyncio.all_tasks() == before
    finally:
        release_cleanup.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_service_cancellation_does_not_skip_next_stop_or_hide_serving_error() -> None:
    original = RuntimeError("serving failed")
    cancelled = asyncio.CancelledError("watcher stop cancelled")
    events: list[str] = []

    def record(step: str) -> None:
        events.append(step)
        if step == "watcher.stop":
            raise cancelled

    with pytest.raises(BaseExceptionGroup) as caught:
        async with manage_runtime(make_resources(record)):
            raise original
    assert caught.value.exceptions == (original, cancelled)
    assert events[-2:] == ["watcher.stop", "queue.stop"]


async def test_caller_timeout_keeps_cleanup_failure_in_its_cause() -> None:
    events: list[str] = []
    stop_error = OSError("watcher stop failed")

    def record(step: str) -> None:
        events.append(step)
        if step == "watcher.stop":
            raise stop_error

    with pytest.raises(TimeoutError) as caught:
        async with asyncio.timeout(0.01):
            async with manage_runtime(make_resources(record)):
                await asyncio.Event().wait()
    cancellation = caught.value.__cause__
    assert isinstance(cancellation, asyncio.CancelledError)
    assert isinstance(cancellation.__cause__, ExceptionGroup)
    assert cancellation.__cause__.exceptions == (stop_error,)
    assert events[-2:] == ["watcher.stop", "queue.stop"]


async def test_cancellation_during_cleanup_keeps_the_original_serving_failure() -> None:
    events: list[str] = []
    stopping = asyncio.Event()
    release = asyncio.Event()
    original = RuntimeError("serving failed before cancellation")

    class GatedService(RecordingService):
        async def stop(self) -> None:
            await super().stop()
            stopping.set()
            await release.wait()

    resources = replace(make_resources(events.append), doujin_watcher=GatedService("watcher", events.append))

    async def run() -> None:
        async with manage_runtime(resources):
            raise original

    task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(stopping.wait(), timeout=2)
        task.cancel("cancel after serving failure")
        release.set()
        with pytest.raises(asyncio.CancelledError) as caught:
            await asyncio.wait_for(task, timeout=2)
        assert task.cancelled()
        assert isinstance(caught.value.__cause__, ExceptionGroup)
        assert caught.value.__cause__.exceptions == (original,)
        assert events[-2:] == ["watcher.stop", "queue.stop"]
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
