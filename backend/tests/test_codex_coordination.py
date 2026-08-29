import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from codex_coordination_mcp import mcp
from services.codex_coordination import (
    CoordinationAuthorizationError,
    CoordinationConflictError,
    CoordinationStore,
)


@pytest.fixture
def store(tmp_path: Path) -> CoordinationStore:
    return CoordinationStore(tmp_path / "coordination.db")


def test_send_list_get_round_trip(store: CoordinationStore) -> None:
    sent = store.send_message(
        sender="mac-codex",
        recipient="windows-codex",
        message="第1巻の差異ページを確認してください",
        subject="第1巻のOCR比較",
        refs={"run_id": 190, "comparison_group_id": "ryuou-v1"},
    )

    assert store.list_messages(recipient="mac-codex") == []
    assert store.list_messages(recipient="windows-codex") == [sent]
    assert store.get_message(sent["id"]) == sent


def test_send_idempotency_reuses_same_message_and_rejects_conflict(
    store: CoordinationStore,
) -> None:
    first = store.send_message(
        sender="mac-codex",
        recipient="windows-codex",
        message="確認してください",
        idempotency_key="comparison-190-request",
    )
    replay = store.send_message(
        sender="mac-codex",
        recipient="windows-codex",
        message="確認してください",
        idempotency_key="comparison-190-request",
    )

    assert replay == first
    assert len(store.list_messages(recipient="windows-codex")) == 1
    with pytest.raises(CoordinationConflictError):
        store.send_message(
            sender="mac-codex",
            recipient="windows-codex",
            message="異なる本文",
            idempotency_key="comparison-190-request",
        )


def test_acknowledge_requires_recipient_and_is_idempotent(
    store: CoordinationStore,
) -> None:
    sent = store.send_message(
        sender="mac-codex",
        recipient="windows-codex",
        message="確認してください",
    )

    with pytest.raises(CoordinationAuthorizationError):
        store.acknowledge_message(message_id=sent["id"], agent_id="mac-codex")
    acknowledged = store.acknowledge_message(message_id=sent["id"], agent_id="windows-codex")
    replay = store.acknowledge_message(message_id=sent["id"], agent_id="windows-codex")

    assert acknowledged["status"] == "acknowledged"
    assert replay == acknowledged
    assert store.list_messages(recipient="windows-codex", status="unread") == []


def test_reply_and_close_enforce_topic_participants(store: CoordinationStore) -> None:
    sent = store.send_message(
        sender="mac-codex",
        recipient="windows-codex",
        message="第1巻を確認してください",
    )

    with pytest.raises(CoordinationAuthorizationError):
        store.reply_message(message_id=sent["id"], sender="mac-codex", message="不正な返信")
    reply = store.reply_message(
        message_id=sent["id"],
        sender="windows-codex",
        message="12ページを要確認と判断しました",
        idempotency_key="reply-page-12",
    )
    closed = store.close_topic(
        topic_id=sent["topic_id"],
        agent_id="mac-codex",
        resolution="12ページをQAキューへ登録",
    )

    assert reply["recipient"] == "mac-codex"
    assert reply["reply_to_id"] == sent["id"]
    assert closed["state"] == "closed"
    with pytest.raises(CoordinationConflictError):
        store.reply_message(
            message_id=sent["id"],
            sender="windows-codex",
            message="close後の返信",
        )


def test_comparison_context_verifies_canonical_sha(store: CoordinationStore) -> None:
    context = {
        "campaign": "device-ab",
        "runs": {"mac": 191, "windows": 190},
        "image_manifest_sha256": "a" * 64,
    }
    saved = store.upsert_comparison_context(comparison_group_id="ryuou-v1", context=context)
    expected_json = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    assert saved["context_sha256"] == hashlib.sha256(expected_json.encode("utf-8")).hexdigest()
    assert store.get_comparison_context("ryuou-v1") == saved
    assert store.get_comparison_context("missing") == {
        "found": False,
        "comparison_group_id": "missing",
    }

    with sqlite3.connect(store.db_path) as connection:
        connection.execute("UPDATE comparison_contexts SET context_json='{}' WHERE comparison_group_id='ryuou-v1'")
    with pytest.raises(CoordinationConflictError):
        store.get_comparison_context("ryuou-v1")


@pytest.mark.asyncio
async def test_mcp_exposes_expected_tools_with_annotations() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert set(tools) == {
        "send_message",
        "list_messages",
        "get_message",
        "ack_message",
        "reply_message",
        "close_topic",
        "get_comparison_context",
    }
    assert tools["list_messages"].annotations is not None
    assert tools["send_message"].annotations is not None
    assert tools["ack_message"].annotations is not None
    assert tools["list_messages"].annotations.readOnlyHint is True
    assert tools["send_message"].annotations.readOnlyHint is False
    assert tools["ack_message"].annotations.idempotentHint is True
