"""One-time opening ledger for B-35 formal OCR holdouts."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LEDGER_SCHEMA_VERSION = "b35-holdout-ledger-v1"


def _timestamp(value: str | None) -> str:
    return value or datetime.now(UTC).isoformat()


def _read_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": LEDGER_SCHEMA_VERSION, "events": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != LEDGER_SCHEMA_VERSION
    ):
        raise ValueError("unsupported formal holdout ledger schema")
    if not isinstance(value.get("events"), list):
        raise ValueError("formal holdout ledger events must be an array")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


@contextmanager
def _ledger_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(
            "formal holdout ledger is locked by another process"
        ) from exc
    os.close(descriptor)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _events_for(
    ledger: Mapping[str, Any], manifest_sha256: str
) -> list[Mapping[str, Any]]:
    return [
        event
        for event in ledger["events"]
        if isinstance(event, Mapping)
        and event.get("manifest_sha256") == manifest_sha256
    ]


def record_sealed_manifest(
    ledger_path: Path,
    manifest: Mapping[str, Any],
    *,
    operator: str,
    occurred_at: str | None = None,
) -> None:
    manifest_sha = str(manifest["manifest_sha256"])
    with _ledger_lock(ledger_path):
        ledger = _read_ledger(ledger_path)
        if _events_for(ledger, manifest_sha):
            raise ValueError("formal holdout manifest is already recorded")
        ledger["events"].append(
            {
                "manifest_sha256": manifest_sha,
                "state": "sealed",
                "operator": operator,
                "occurred_at": _timestamp(occurred_at),
            }
        )
        _write_json_atomic(ledger_path, ledger)


def open_formal_holdout(
    ledger_path: Path,
    manifest_sha256: str,
    *,
    operator: str,
    reason: str,
    occurred_at: str | None = None,
) -> None:
    with _ledger_lock(ledger_path):
        ledger = _read_ledger(ledger_path)
        events = _events_for(ledger, manifest_sha256)
        if not events or events[-1].get("state") != "sealed":
            if any(event.get("state") == "opened" for event in events):
                raise ValueError("formal holdout was already opened")
            raise ValueError("formal holdout must be recorded as sealed before opening")
        ledger["events"].append(
            {
                "manifest_sha256": manifest_sha256,
                "state": "opened",
                "operator": operator,
                "reason": reason,
                "occurred_at": _timestamp(occurred_at),
            }
        )
        _write_json_atomic(ledger_path, ledger)


def retire_formal_holdout_to_tuning(
    ledger_path: Path,
    manifest: Mapping[str, Any],
    *,
    operator: str,
    reason: str,
    occurred_at: str | None = None,
) -> None:
    if not operator.strip() or not reason.strip():
        raise ValueError("formal holdout retirement requires operator and reason")
    manifest_sha = str(manifest["manifest_sha256"])
    with _ledger_lock(ledger_path):
        ledger = _read_ledger(ledger_path)
        events = _events_for(ledger, manifest_sha)
        if any(event.get("state") == "retired_to_tuning" for event in events):
            raise ValueError("formal holdout is already retired to tuning")
        if not events or events[-1].get("state") != "opened":
            raise ValueError("formal holdout must be opened before retirement")
        ledger["events"].append(
            {
                "manifest_sha256": manifest_sha,
                "state": "retired_to_tuning",
                "operator": operator,
                "reason": reason,
                "occurred_at": _timestamp(occurred_at),
            }
        )
        _write_json_atomic(ledger_path, ledger)
