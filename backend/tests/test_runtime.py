"""Injected resources can run independently in the same event loop."""

from bootstrap.runtime import RuntimeResources, manage_runtime
from tests.test_main_lifespan import RecordingService


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
