"""Codex端末間メッセージを専用SQLiteへ保存する。"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_BODY_CHARS = 65_536
_MAX_SUBJECT_CHARS = 256
_MAX_RESOLUTION_CHARS = 8_192
_MAX_IDEMPOTENCY_KEY_CHARS = 256
_MAX_REFS_BYTES = 16_384
_MAX_CONTEXT_BYTES = 262_144


class CoordinationValidationError(ValueError):
    """入力値が連携契約を満たさない。"""


class CoordinationNotFoundError(LookupError):
    """対象messageまたはtopicが存在しない。"""


class CoordinationConflictError(RuntimeError):
    """冪等キーまたは状態遷移が既存状態と競合した。"""


class CoordinationAuthorizationError(PermissionError):
    """agentが対象messageまたはtopicの参加者ではない。"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validate_identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise CoordinationValidationError(f"{name} must match {_IDENTIFIER_RE.pattern}")
    return value


def _validate_text(value: str, name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise CoordinationValidationError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise CoordinationValidationError(f"{name} must not be empty")
    if len(normalized) > limit:
        raise CoordinationValidationError(f"{name} exceeds {limit} characters")
    return normalized


def _canonical_object(
    value: dict[str, Any] | None,
    *,
    name: str,
    max_bytes: int,
) -> tuple[dict[str, Any], str]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise CoordinationValidationError(f"{name} must be a JSON object")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise CoordinationValidationError(f"{name} must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise CoordinationValidationError(f"{name} exceeds {max_bytes} bytes")
    return value, encoded


class CoordinationStore:
    """短いtransaction単位で専用SQLiteを操作する。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS topics (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('open', 'closed')),
                    created_at TEXT NOT NULL,
                    closed_at TEXT,
                    closed_by TEXT,
                    resolution TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL REFERENCES topics(id),
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    body TEXT NOT NULL,
                    refs_json TEXT NOT NULL DEFAULT '{}',
                    reply_to_id TEXT REFERENCES messages(id),
                    status TEXT NOT NULL CHECK (status IN ('unread', 'acknowledged')),
                    created_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    acknowledged_by TEXT,
                    idempotency_key TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_sender_idempotency
                ON messages(sender, idempotency_key)
                WHERE idempotency_key IS NOT NULL;

                CREATE INDEX IF NOT EXISTS ix_messages_recipient_status_created
                ON messages(recipient, status, created_at DESC);

                CREATE INDEX IF NOT EXISTS ix_messages_topic_created
                ON messages(topic_id, created_at);

                CREATE TABLE IF NOT EXISTS comparison_contexts (
                    comparison_group_id TEXT PRIMARY KEY,
                    context_json TEXT NOT NULL,
                    context_sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                PRAGMA user_version=1;
                """
            )

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "topic_id": str(row["topic_id"]),
            "sender": str(row["sender"]),
            "recipient": str(row["recipient"]),
            "message": str(row["body"]),
            "refs": json.loads(str(row["refs_json"])),
            "reply_to_id": row["reply_to_id"],
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
            "acknowledged_at": row["acknowledged_at"],
            "acknowledged_by": row["acknowledged_by"],
            "idempotency_key": row["idempotency_key"],
        }

    @staticmethod
    def _topic_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "subject": str(row["subject"]),
            "state": str(row["state"]),
            "created_at": str(row["created_at"]),
            "closed_at": row["closed_at"],
            "closed_by": row["closed_by"],
            "resolution": row["resolution"],
        }

    @staticmethod
    def _load_message(connection: sqlite3.Connection, message_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if row is None:
            raise CoordinationNotFoundError(f"message not found: {message_id}")
        return row

    @staticmethod
    def _load_topic(connection: sqlite3.Connection, topic_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
        if row is None:
            raise CoordinationNotFoundError(f"topic not found: {topic_id}")
        return row

    @staticmethod
    def _require_open_topic(topic: sqlite3.Row) -> None:
        if topic["state"] != "open":
            raise CoordinationConflictError(f"topic is closed: {topic['id']}")

    @staticmethod
    def _is_participant(connection: sqlite3.Connection, topic_id: str, agent_id: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM messages WHERE topic_id=? AND (sender=? OR recipient=?) LIMIT 1",
                (topic_id, agent_id, agent_id),
            ).fetchone()
            is not None
        )

    @staticmethod
    def _existing_idempotent(
        connection: sqlite3.Connection,
        *,
        sender: str,
        idempotency_key: str | None,
        recipient: str,
        body: str,
        refs_json: str,
        topic_id: str | None,
        reply_to_id: str | None,
    ) -> sqlite3.Row | None:
        if idempotency_key is None:
            return None
        existing = connection.execute(
            "SELECT * FROM messages WHERE sender=? AND idempotency_key=?",
            (sender, idempotency_key),
        ).fetchone()
        if existing is None:
            return None
        same = (
            existing["recipient"] == recipient
            and existing["body"] == body
            and existing["refs_json"] == refs_json
            and (topic_id is None or existing["topic_id"] == topic_id)
            and existing["reply_to_id"] == reply_to_id
        )
        if not same:
            raise CoordinationConflictError("idempotency_key is already used for a different message")
        return existing

    def send_message(
        self,
        *,
        sender: str,
        recipient: str,
        message: str,
        topic_id: str | None = None,
        subject: str | None = None,
        refs: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        sender = _validate_identifier(sender, "sender")
        recipient = _validate_identifier(recipient, "recipient")
        if sender == recipient:
            raise CoordinationValidationError("sender and recipient must differ")
        body = _validate_text(message, "message", _MAX_BODY_CHARS)
        _, refs_json = _canonical_object(refs, name="refs", max_bytes=_MAX_REFS_BYTES)
        if topic_id is not None:
            topic_id = _validate_identifier(topic_id, "topic_id")
        if idempotency_key is not None:
            idempotency_key = _validate_text(
                idempotency_key,
                "idempotency_key",
                _MAX_IDEMPOTENCY_KEY_CHARS,
            )
        normalized_subject = (
            _validate_text(subject, "subject", _MAX_SUBJECT_CHARS) if subject is not None else f"Message from {sender}"
        )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._existing_idempotent(
                connection,
                sender=sender,
                idempotency_key=idempotency_key,
                recipient=recipient,
                body=body,
                refs_json=refs_json,
                topic_id=topic_id,
                reply_to_id=None,
            )
            if existing is not None:
                return self._message_from_row(existing)

            created_at = _now()
            if topic_id is None:
                topic_id = str(uuid.uuid4())
                connection.execute(
                    "INSERT INTO topics (id, subject, state, created_at) VALUES (?, ?, 'open', ?)",
                    (topic_id, normalized_subject, created_at),
                )
            else:
                topic = self._load_topic(connection, topic_id)
                self._require_open_topic(topic)
                if not self._is_participant(connection, topic_id, sender):
                    raise CoordinationAuthorizationError(f"agent is not a topic participant: {sender}")

            message_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO messages "
                "(id, topic_id, sender, recipient, body, refs_json, status, "
                "created_at, idempotency_key) "
                "VALUES (?, ?, ?, ?, ?, ?, 'unread', ?, ?)",
                (
                    message_id,
                    topic_id,
                    sender,
                    recipient,
                    body,
                    refs_json,
                    created_at,
                    idempotency_key,
                ),
            )
            return self._message_from_row(self._load_message(connection, message_id))

    def list_messages(
        self,
        *,
        recipient: str,
        status: str = "unread",
        topic_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        recipient = _validate_identifier(recipient, "recipient")
        if status not in {"unread", "acknowledged", "all"}:
            raise CoordinationValidationError("status must be unread, acknowledged, or all")
        if topic_id is not None:
            topic_id = _validate_identifier(topic_id, "topic_id")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise CoordinationValidationError("limit must be between 1 and 100")

        clauses = ["recipient=?"]
        params: list[Any] = [recipient]
        if status != "all":
            clauses.append("status=?")
            params.append(status)
        if topic_id is not None:
            clauses.append("topic_id=?")
            params.append(topic_id)
        params.append(limit)
        query = "SELECT * FROM messages WHERE " + " AND ".join(clauses) + " ORDER BY created_at DESC, id DESC LIMIT ?"
        with self._connect() as connection:
            return [self._message_from_row(row) for row in connection.execute(query, params).fetchall()]

    def get_message(self, message_id: str) -> dict[str, Any]:
        message_id = _validate_identifier(message_id, "message_id")
        with self._connect() as connection:
            return self._message_from_row(self._load_message(connection, message_id))

    def acknowledge_message(self, *, message_id: str, agent_id: str) -> dict[str, Any]:
        message_id = _validate_identifier(message_id, "message_id")
        agent_id = _validate_identifier(agent_id, "agent_id")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            message = self._load_message(connection, message_id)
            if message["recipient"] != agent_id:
                raise CoordinationAuthorizationError("only the message recipient can acknowledge it")
            if message["status"] == "acknowledged":
                if message["acknowledged_by"] != agent_id:
                    raise CoordinationConflictError("message was acknowledged by another agent")
                return self._message_from_row(message)
            connection.execute(
                "UPDATE messages SET status='acknowledged', acknowledged_at=?, acknowledged_by=? WHERE id=?",
                (_now(), agent_id, message_id),
            )
            return self._message_from_row(self._load_message(connection, message_id))

    def reply_message(
        self,
        *,
        message_id: str,
        sender: str,
        message: str,
        refs: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        message_id = _validate_identifier(message_id, "message_id")
        sender = _validate_identifier(sender, "sender")
        body = _validate_text(message, "message", _MAX_BODY_CHARS)
        _, refs_json = _canonical_object(refs, name="refs", max_bytes=_MAX_REFS_BYTES)
        if idempotency_key is not None:
            idempotency_key = _validate_text(
                idempotency_key,
                "idempotency_key",
                _MAX_IDEMPOTENCY_KEY_CHARS,
            )

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            original = self._load_message(connection, message_id)
            if original["recipient"] != sender:
                raise CoordinationAuthorizationError("only the original recipient can reply")
            topic = self._load_topic(connection, str(original["topic_id"]))
            self._require_open_topic(topic)
            existing = self._existing_idempotent(
                connection,
                sender=sender,
                idempotency_key=idempotency_key,
                recipient=str(original["sender"]),
                body=body,
                refs_json=refs_json,
                topic_id=str(original["topic_id"]),
                reply_to_id=message_id,
            )
            if existing is not None:
                return self._message_from_row(existing)

            reply_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO messages "
                "(id, topic_id, sender, recipient, body, refs_json, reply_to_id, "
                "status, created_at, idempotency_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'unread', ?, ?)",
                (
                    reply_id,
                    original["topic_id"],
                    sender,
                    original["sender"],
                    body,
                    refs_json,
                    message_id,
                    _now(),
                    idempotency_key,
                ),
            )
            return self._message_from_row(self._load_message(connection, reply_id))

    def close_topic(self, *, topic_id: str, agent_id: str, resolution: str) -> dict[str, Any]:
        topic_id = _validate_identifier(topic_id, "topic_id")
        agent_id = _validate_identifier(agent_id, "agent_id")
        resolution = _validate_text(resolution, "resolution", _MAX_RESOLUTION_CHARS)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            topic = self._load_topic(connection, topic_id)
            if not self._is_participant(connection, topic_id, agent_id):
                raise CoordinationAuthorizationError(f"agent is not a topic participant: {agent_id}")
            if topic["state"] == "closed":
                if topic["closed_by"] != agent_id or topic["resolution"] != resolution:
                    raise CoordinationConflictError("topic is already closed with a different resolution")
                return self._topic_from_row(topic)
            connection.execute(
                "UPDATE topics SET state='closed', closed_at=?, closed_by=?, resolution=? WHERE id=?",
                (_now(), agent_id, resolution, topic_id),
            )
            return self._topic_from_row(self._load_topic(connection, topic_id))

    def upsert_comparison_context(self, *, comparison_group_id: str, context: dict[str, Any]) -> dict[str, Any]:
        comparison_group_id = _validate_identifier(comparison_group_id, "comparison_group_id")
        normalized_context, context_json = _canonical_object(context, name="context", max_bytes=_MAX_CONTEXT_BYTES)
        digest = hashlib.sha256(context_json.encode("utf-8")).hexdigest()
        updated_at = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO comparison_contexts "
                "(comparison_group_id, context_json, context_sha256, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(comparison_group_id) DO UPDATE SET "
                "context_json=excluded.context_json, "
                "context_sha256=excluded.context_sha256, "
                "updated_at=excluded.updated_at",
                (comparison_group_id, context_json, digest, updated_at),
            )
        return {
            "found": True,
            "comparison_group_id": comparison_group_id,
            "context": normalized_context,
            "context_sha256": digest,
            "updated_at": updated_at,
        }

    def get_comparison_context(self, comparison_group_id: str) -> dict[str, Any]:
        comparison_group_id = _validate_identifier(comparison_group_id, "comparison_group_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM comparison_contexts WHERE comparison_group_id=?",
                (comparison_group_id,),
            ).fetchone()
        if row is None:
            return {
                "found": False,
                "comparison_group_id": comparison_group_id,
            }
        context_json = str(row["context_json"])
        actual_digest = hashlib.sha256(context_json.encode("utf-8")).hexdigest()
        if actual_digest != row["context_sha256"]:
            raise CoordinationConflictError(f"comparison context SHA mismatch: {comparison_group_id}")
        context = json.loads(context_json)
        if not isinstance(context, dict):
            raise CoordinationConflictError(f"comparison context is not an object: {comparison_group_id}")
        return {
            "found": True,
            "comparison_group_id": comparison_group_id,
            "context": context,
            "context_sha256": actual_digest,
            "updated_at": str(row["updated_at"]),
        }
