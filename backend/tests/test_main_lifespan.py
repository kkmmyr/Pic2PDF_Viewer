"""Freeze the registered lifespan ordering without starting real resources."""

from collections.abc import Callable

import pytest

STEPS = ["meta", "novel", "kindle", "queue.start", "watcher.start", "serve", "watcher.stop", "queue.stop"]


class RecordingService:
    def __init__(self, name: str, record: Callable[[str], None]) -> None:
        self.name = name
        self.record = record

    async def start(self) -> None:
        self.record(f"{self.name}.start")

    async def stop(self) -> None:
        self.record(f"{self.name}.stop")


def install_resources(monkeypatch: pytest.MonkeyPatch, events: list[str], fail_at: str | None = None) -> None:
    import main

    def record(step: str) -> None:
        events.append(step)
        if step == fail_at:
            raise RuntimeError(step)

    monkeypatch.setattr(main, "init_db", lambda: record("meta"))
    monkeypatch.setattr(main, "upgrade_head", lambda: record("novel"))
    monkeypatch.setattr(main, "upgrade_kindle_catalog", lambda: record("kindle"))
    monkeypatch.setattr(main, "job_queue", RecordingService("queue", record))
    monkeypatch.setattr(main, "doujin_watcher", RecordingService("watcher", record))


async def test_registered_lifespan_initializes_and_stops_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    import main

    events: list[str] = []
    install_resources(monkeypatch, events)
    async with main.app.router.lifespan_context(main.app):
        events.append("serve")
    assert events == STEPS


async def test_lifespan_stops_resources_when_serving_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import main

    events: list[str] = []
    install_resources(monkeypatch, events)
    with pytest.raises(RuntimeError, match="request failed"):
        async with main.app.router.lifespan_context(main.app):
            events.append("serve")
            raise RuntimeError("request failed")
    assert events == STEPS


@pytest.mark.parametrize("fail_at", [step for step in STEPS if step != "serve"])
async def test_lifespan_propagates_resource_failure_at_current_boundary(
    monkeypatch: pytest.MonkeyPatch, fail_at: str
) -> None:
    import main

    events: list[str] = []
    install_resources(monkeypatch, events, fail_at)
    with pytest.raises(RuntimeError, match=fail_at):
        async with main.app.router.lifespan_context(main.app):
            events.append("serve")
    # Partial-start and stop-failure cleanup is not silently changed by extraction.
    assert events == STEPS[: STEPS.index(fail_at) + 1]


async def test_lifespan_resolves_resources_for_each_session() -> None:
    import main

    first: list[str] = []
    second: list[str] = []
    for events in (first, second):
        with pytest.MonkeyPatch.context() as patch:
            install_resources(patch, events)
            async with main.app.router.lifespan_context(main.app):
                events.append("serve")
    assert first == second == STEPS
