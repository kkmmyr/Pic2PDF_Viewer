#!/usr/bin/env python3
"""Mac / Windows Codex間連携用のStreamable HTTP MCPサーバー。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from config.codex_coordination import codex_coordination_settings
from services.codex_coordination import CoordinationStore

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
_IDEMPOTENT_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

mcp = FastMCP(
    "codex-coordination",
    instructions=(
        "MacとWindowsのCodex間で非同期メッセージを中継します。"
        "agent IDはmac-codexまたはwindows-codexを使ってください。"
        "受信したらack_message、回答にはreply_messageを使い、同じ送信を再試行する場合は"
        "idempotency_keyを再利用してください。このサービスはOCRの承認・公開を行いません。"
    ),
    host=codex_coordination_settings.host,
    port=codex_coordination_settings.port,
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    log_level=codex_coordination_settings.log_level,
)


@lru_cache(maxsize=1)
def _store() -> CoordinationStore:
    return CoordinationStore(codex_coordination_settings.db_path)


@mcp.tool(annotations=_WRITE)
def send_message(
    sender: str,
    recipient: str,
    message: str,
    topic_id: str | None = None,
    subject: str | None = None,
    refs: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """相手Codexへ新しいメッセージを送る。"""
    return _store().send_message(
        sender=sender,
        recipient=recipient,
        message=message,
        topic_id=topic_id,
        subject=subject,
        refs=refs,
        idempotency_key=idempotency_key,
    )


@mcp.tool(annotations=_READ_ONLY)
def list_messages(
    recipient: str,
    status: str = "unread",
    topic_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """指定agent宛てのメッセージを新しい順に取得する。"""
    return _store().list_messages(
        recipient=recipient,
        status=status,
        topic_id=topic_id,
        limit=limit,
    )


@mcp.tool(annotations=_READ_ONLY)
def get_message(message_id: str) -> dict[str, Any]:
    """message IDで本文・参照・状態を取得する。"""
    return _store().get_message(message_id)


@mcp.tool(annotations=_IDEMPOTENT_WRITE)
def ack_message(message_id: str, agent_id: str) -> dict[str, Any]:
    """受信者本人がメッセージを確認済みにする。"""
    return _store().acknowledge_message(message_id=message_id, agent_id=agent_id)


@mcp.tool(annotations=_WRITE)
def reply_message(
    message_id: str,
    sender: str,
    message: str,
    refs: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """元メッセージのtopicを維持して送信元へ返信する。"""
    return _store().reply_message(
        message_id=message_id,
        sender=sender,
        message=message,
        refs=refs,
        idempotency_key=idempotency_key,
    )


@mcp.tool(annotations=_IDEMPOTENT_WRITE)
def close_topic(topic_id: str, agent_id: str, resolution: str) -> dict[str, Any]:
    """topic参加者が解決内容を記録してtopicを閉じる。"""
    return _store().close_topic(
        topic_id=topic_id,
        agent_id=agent_id,
        resolution=resolution,
    )


@mcp.tool(annotations=_READ_ONLY)
def get_comparison_context(comparison_group_id: str) -> dict[str, Any]:
    """OCR比較コーディネーターが登録した固定文脈を取得する。"""
    return _store().get_comparison_context(comparison_group_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
