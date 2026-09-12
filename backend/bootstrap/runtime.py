"""Manage explicitly supplied application resources in their established order."""

import asyncio
import math
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol


class ManagedService(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


@dataclass(frozen=True)
class RuntimeResources:
    initialize_meta: Callable[[], None]
    migrate_novel: Callable[[], None]
    migrate_kindle: Callable[[], None]
    job_queue: ManagedService
    doujin_watcher: ManagedService
    stop_timeout: float = 30.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.stop_timeout) or self.stop_timeout <= 0:
            raise ValueError("stop_timeout must be finite and positive")


async def _stop_resources(started: list[tuple[str, ManagedService]], timeout: float) -> list[BaseException]:
    failures: list[BaseException] = []
    for name, service in reversed(started):
        try:
            async with asyncio.timeout(timeout):
                await service.stop()
        except BaseException as error:
            # Cancellation raised by one service must not skip the remaining resources.
            error.add_note(f"Runtime resource stop failed: {name}")
            failures.append(error)
    return failures


async def _await_cleanup(task: asyncio.Task[list[BaseException]]) -> asyncio.CancelledError | None:
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            # Keep the cleanup task alive even if the owner is cancelled repeatedly.
            if cancellation is None:
                cancellation = error
    return cancellation


def _raise_failures(
    primary: BaseException | None,
    failures: list[BaseException],
    cancellation: asyncio.CancelledError | None,
) -> None:
    if isinstance(primary, asyncio.CancelledError):
        cancellation = primary
    elif primary is not None:
        failures.insert(0, primary)
    if cancellation is not None:
        if failures:
            raise cancellation from BaseExceptionGroup("Runtime failures during cancellation", failures)
        raise cancellation
    if len(failures) == 1:
        raise failures[0]
    if failures:
        raise BaseExceptionGroup("Runtime startup, serving or cleanup failures", failures)


@asynccontextmanager
async def manage_runtime(resources: RuntimeResources) -> AsyncIterator[None]:
    started: list[tuple[str, ManagedService]] = []
    primary: BaseException | None = None
    try:
        resources.initialize_meta()
        resources.migrate_novel()
        resources.migrate_kindle()
        for name, service in (("queue", resources.job_queue), ("watcher", resources.doujin_watcher)):
            await service.start()
            started.append((name, service))
        yield
    except BaseException as error:
        primary = error
    if started:
        cleanup = asyncio.create_task(_stop_resources(started, resources.stop_timeout), name="RuntimeCleanup")
        cancellation = await _await_cleanup(cleanup)
        _raise_failures(primary, cleanup.result(), cancellation)
    elif primary is not None:
        raise primary
