"""読書会LLM streamをsegment/turn domain eventへ変換する。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from .discussion_parser import SEGMENT_RE, TURN_RE

ChatStream = Callable[..., AsyncIterator[dict[str, Any]]]


class DiscussionStreamParser:
    """chunk境界を跨ぐmarkerを保持する増分parser。"""

    def __init__(self) -> None:
        self.buffer = ""
        self.current_speaker: str | None = None
        self.current_segment: str | None = None

    def feed(self, text: str) -> list[dict[str, object]]:
        self.buffer += text
        return self._drain(at_end=False)

    def finish(self) -> list[dict[str, object]]:
        events = self._drain(at_end=True)
        turn = self._flush_turn(self.buffer)
        self.buffer = ""
        if turn is not None:
            events.append(turn)
        return events

    def _drain(self, *, at_end: bool) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        while True:
            turn_match = TURN_RE.search(self.buffer)
            segment_match = SEGMENT_RE.search(self.buffer)
            if turn_match is None and segment_match is None:
                return events
            if segment_match is not None and (turn_match is None or segment_match.start() < turn_match.start()):
                if not at_end and segment_match.end() == len(self.buffer) and self.buffer[-1] not in "]>":
                    return events
                turn = self._flush_turn(self.buffer[: segment_match.start()])
                if turn is not None:
                    events.append(turn)
                self.current_speaker = None
                self.current_segment = segment_match.group(1)
                events.append({"type": "segment", "id": self.current_segment})
                self.buffer = self.buffer[segment_match.end() :]
                continue
            if turn_match is None:
                return events
            turn = self._flush_turn(self.buffer[: turn_match.start()])
            if turn is not None:
                events.append(turn)
            self.current_speaker = turn_match.group(1)
            self.buffer = self.buffer[turn_match.end() :]

    def _flush_turn(self, text: str) -> dict[str, object] | None:
        value = text.strip()
        if self.current_speaker is None or not value:
            return None
        return {
            "type": "turn",
            "speaker": self.current_speaker,
            "text": value,
            "segment": self.current_segment,
        }


async def stream_discussion_events(
    messages: list[dict[str, object]],
    *,
    chat_stream: ChatStream,
    model: str,
    options: dict[str, object],
) -> AsyncIterator[dict[str, object]]:
    parser = DiscussionStreamParser()
    async for event in chat_stream(messages, model=model, options=options):
        response = event.get("response")
        if isinstance(response, str) and response:
            for parsed in parser.feed(response):
                yield parsed
        if event.get("done"):
            for parsed in parser.finish():
                yield parsed
            return
