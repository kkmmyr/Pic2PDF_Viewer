"""Manage explicitly supplied application resources in their established order."""

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


@asynccontextmanager
async def manage_runtime(resources: RuntimeResources) -> AsyncIterator[None]:
    resources.initialize_meta()
    resources.migrate_novel()
    resources.migrate_kindle()
    await resources.job_queue.start()
    await resources.doujin_watcher.start()
    # Preserve the existing startup/cleanup boundary; partial-start recovery is separate.
    try:
        yield
    finally:
        await resources.doujin_watcher.stop()
        await resources.job_queue.stop()
