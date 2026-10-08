#!/usr/bin/env python3
"""Locked, offline-only OCR reservations; never accesses a database or dispatches chats."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import posixpath
import tempfile
import uuid

SCHEMA = "ocr-offline-ledger-v1"
STATUSES = {
    "reserved",
    "dispatched",
    "running",
    "dispatch_uncertain",
    "verifying",
    "completed",
    "failed",
}
TERMINAL = {"completed", "failed"}
RUN_STATUSES = {"active", "exhausted", "quota_stop", "user_stopped"}
IMMUTABLE = {
    "key",
    "name",
    "source_path",
    "root",
    "pages",
    "number",
    "batch",
    "batch_number",
    "global_sequence",
    "dispatch_token",
    "title",
    "imported",
    "created_at",
    "model",
    "reasoning_effort",
    "thread_id",
    "host_id",
}


class LedgerError(ValueError):
    """An invalid ledger or operation; no authoritative write is performed."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_key(source_path: str) -> str:
    if not isinstance(source_path, str) or not source_path.startswith("/"):
        raise LedgerError("source_path must be an absolute POSIX path")
    return hashlib.sha256(posixpath.normpath(source_path).encode("utf-8")).hexdigest()


def integer(value, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise LedgerError(f"{label} must be an integer >= {minimum}")
    return value


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LedgerError(f"Cannot read JSON {path}: {exc}") from exc


def completed_check(book: dict) -> None:
    if book.get("imported"):
        return
    counts = book.get("stage_counts", {})
    pages = book["pages"]
    stages = [
        counts.get("raw", counts.get("initial", counts.get("ocr"))),
        counts.get("review"),
        counts.get("evaluation", counts.get("qa")),
        counts.get("final"),
    ]
    if any(type(value) is not int or value != pages for value in stages):
        raise LedgerError("completed requires four stages at N/N")
    verification = book.get("verification")
    if not isinstance(verification, dict) or verification.get("verified") is not True:
        raise LedgerError("completed requires manager verification.verified=true")
    for name in ("known_unresolved_body", "known_unresolved_findings"):
        value = book.get(name)
        if not (
            type(value) is int and value == 0 or isinstance(value, list) and not value
        ):
            raise LedgerError(f"completed requires {name}=0 or []")
    if book.get("db_reflection") != "held":
        raise LedgerError("completed requires DB reflection held")


def validate(ledger: dict) -> None:
    if not isinstance(ledger, dict) or ledger.get("schema") != SCHEMA:
        raise LedgerError("Invalid ledger schema")
    if ledger.get("run_status") not in RUN_STATUSES:
        raise LedgerError("Invalid run status")
    integer(ledger.get("next_batch_number"), "next_batch_number", 1)
    integer(ledger.get("revision"), "revision")
    books, batches, events = (
        ledger.get(name) for name in ("books", "batches", "events")
    )
    if not all(isinstance(value, list) for value in (books, batches, events)):
        raise LedgerError("books, batches and events must be lists")
    keys, sequences, roots, chats = set(), set(), set(), {}
    for book in books:
        if not isinstance(book, dict) or book.get("status") not in STATUSES:
            raise LedgerError("Invalid book status")
        if not isinstance(book.get("name"), str) or not book["name"].strip():
            raise LedgerError("Book name must be nonempty")
        if "imported" in book and type(book["imported"]) is not bool:
            raise LedgerError("imported must be boolean")
        key = source_key(book.get("source_path"))
        if book.get("key") != key or key in keys:
            raise LedgerError("Duplicate or mismatched source key")
        keys.add(key)
        integer(book.get("pages"), "pages", 1)
        seq = integer(book.get("global_sequence"), "global_sequence", 1)
        if seq in sequences:
            raise LedgerError("Duplicate global_sequence")
        sequences.add(seq)
        if (
            not isinstance(book.get("root"), str)
            or not Path(book["root"]).is_absolute()
        ):
            raise LedgerError("Book root must be absolute")
        normalized_root = str(Path(book["root"]).resolve())
        if normalized_root in roots:
            raise LedgerError("Book roots must be separate")
        roots.add(normalized_root)
        thread_id = book.get("thread_id")
        if thread_id is not None:
            imported = book.get("imported") is True
            if not isinstance(thread_id, str) or not thread_id.strip():
                raise LedgerError("Invalid or duplicate chat binding")
            if thread_id in chats and not (imported and chats[thread_id]):
                raise LedgerError("Invalid or duplicate chat binding")
            chats[thread_id] = imported
        if not isinstance(book.get("stage_counts"), dict):
            raise LedgerError("stage_counts must be an object")
        for value in book["stage_counts"].values():
            integer(value, "stage count")
            if value > book["pages"]:
                raise LedgerError("Stage count exceeds pages")
        if book.get("db_reflection") != "held":
            raise LedgerError("DB reflection must remain held")
        if book.get("imported") and book["status"] not in TERMINAL:
            raise LedgerError("Imported records must stay terminal")
        if book["status"] == "failed" and (
            not isinstance(book.get("failure_reason"), str)
            or not book["failure_reason"].strip()
        ):
            raise LedgerError("failed requires a nonempty failure_reason")
        if book["status"] == "completed":
            completed_check(book)
    batch_numbers, claimed = set(), set()
    for batch in batches:
        if not isinstance(batch, dict):
            raise LedgerError("Invalid batch")
        number = integer(batch.get("number"), "batch number", 1)
        if number in batch_numbers or number >= ledger["next_batch_number"]:
            raise LedgerError("Duplicate or invalid batch number")
        batch_numbers.add(number)
        members = batch.get("book_keys")
        if (
            not isinstance(members, list)
            or not members
            or len(members) != len(set(members))
        ):
            raise LedgerError("Invalid batch book_keys")
        for key in members:
            if key not in keys or key in claimed:
                raise LedgerError("Missing or duplicate batch member")
            book = next(book for book in books if book["key"] == key)
            if book.get("batch_number") != number:
                raise LedgerError("Book/batch mismatch")
            claimed.add(key)
    if any(not book.get("imported") and book["key"] not in claimed for book in books):
        raise LedgerError("Non-imported book missing from batch")
    active_batches = {
        book.get("batch_number") for book in books if book["status"] not in TERMINAL
    }
    if len(active_batches) > 1:
        raise LedgerError("More than one active batch")
    if any(not isinstance(event, dict) for event in events):
        raise LedgerError("Invalid events")


def atomic_write(path: Path, content: str) -> None:
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def markdown(ledger: dict) -> str:
    def cell(value):
        return (
            str(value if value is not None else "—")
            .replace("|", "\\|")
            .replace("\n", " ")
        )

    lines = [
        "# 隔離OCR継続台帳",
        "",
        f"状態: {ledger['run_status']} / revision: {ledger['revision']}",
        "",
        "| 通番 | 書籍 | 画面 | バッチ | チャット | 状態 | 工程 | 未解決本文 | 未補正指摘 | 非本文保留 | 保存先・成果物 | 失敗理由 |",
        "|---:|---|---:|---:|---|---|---|---:|---:|---:|---|---|",
    ]
    for book in sorted(ledger["books"], key=lambda item: item["global_sequence"]):
        artifacts = book.get("artifacts", {})
        links = [f"[保存先](<{book['root']}>)"]
        if isinstance(artifacts, dict):
            for label, names in (
                ("report", ("report", "report_path")),
                ("body", ("body", "body_text", "body_txt", "body_text_path")),
                ("bundle", ("bundle", "candidate_bundle", "bundle_path")),
            ):
                artifact = next(
                    (artifacts[name] for name in names if name in artifacts), None
                )
                if isinstance(artifact, dict):
                    artifact = artifact.get("path", artifact.get("file"))
                if isinstance(artifact, str) and artifact:
                    target = Path(artifact)
                    if not target.is_absolute():
                        target = Path(book["root"]) / target
                    links.append(f"[{label}](<{target}>)")

        def count(name):
            value = book.get(name)
            return len(value) if isinstance(value, list) else value

        values = [
            book["global_sequence"],
            book["name"],
            book["pages"],
            book.get("batch_number"),
            book.get("thread_id"),
            book["status"],
            json.dumps(book["stage_counts"], ensure_ascii=False),
            count("known_unresolved_body"),
            count("known_unresolved_findings"),
            count("nonbody_holds"),
            " · ".join(links),
            book.get("failure_reason"),
        ]
        lines.append("| " + " | ".join(map(cell, values)) + " |")
    return "\n".join(lines) + "\n"


def project(root: Path, ledger: dict) -> None:
    atomic_write(
        root / "events.jsonl",
        "".join(
            json.dumps(event, ensure_ascii=False) + "\n" for event in ledger["events"]
        ),
    )
    atomic_write(root / "LEDGER.md", markdown(ledger))


def save(root: Path, ledger: dict, action: str, details: dict) -> None:
    ledger["revision"] += 1
    ledger["updated_at"] = now()
    ledger["events"].append(
        {
            "revision": ledger["revision"],
            "at": ledger["updated_at"],
            "action": action,
            **details,
        }
    )
    validate(ledger)
    atomic_write(
        root / "ledger.json", json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
    )
    # The JSON ledger is authoritative. A crash here is repaired by show or the next mutation.
    project(root, ledger)


@contextmanager
def locked(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".ledger.lock").open("a", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def operate(root: Path, command: str, **options):
    root = root.resolve()
    with locked(root):
        path = root / "ledger.json"
        if command == "init":
            if path.exists():
                raise LedgerError("Ledger already exists; use show to resume")
            imports = read_json(Path(options["imports"]))
            if not isinstance(imports, list):
                raise LedgerError("imports must be a list")
            stamp = now()
            ledger = {
                "schema": SCHEMA,
                "run_status": "active",
                "run_reason": None,
                "next_batch_number": options.get("next_batch_number", 2),
                "revision": 0,
                "created_at": stamp,
                "books": [],
                "batches": [],
                "events": [],
            }
            for index, record in enumerate(imports, 1):
                if (
                    not isinstance(record, dict)
                    or record.get("status", "completed") not in TERMINAL
                ):
                    raise LedgerError("Imports must be completed/failed records")
                book = {
                    **record,
                    "key": source_key(record.get("source_path")),
                    "imported": True,
                    "status": record.get("status", "completed"),
                    "global_sequence": index,
                    "stage_counts": record.get("stage_counts", {}),
                    "db_reflection": "held",
                    "created_at": stamp,
                    "updated_at": stamp,
                }
                ledger["books"].append(book)
            save(root, ledger, "init", {"imported": len(imports)})
            return ledger
        ledger = read_json(path)
        validate(ledger)
        if command == "show":
            project(root, ledger)
            return ledger
        if command == "state":
            if options["status"] not in RUN_STATUSES:
                raise LedgerError("Invalid run status")
            ledger["run_status"] = options["status"]
            ledger["run_reason"] = options.get("reason")
            save(
                root,
                ledger,
                "state",
                {"status": options["status"], "reason": options.get("reason")},
            )
            return ledger
        if command == "reserve":
            if ledger["run_status"] != "active":
                raise LedgerError("Run is stopped; reservations are forbidden")
            size = integer(options.get("size", 10), "size", 1)
            if size > 10:
                raise LedgerError("A batch may contain at most 10 books")
            active = [
                book for book in ledger["books"] if book["status"] not in TERMINAL
            ]
            if active:
                return {"created": False, "books": active}
            inventory = read_json(Path(options["inventory"]))
            if not isinstance(inventory, list):
                raise LedgerError("inventory must be a list")
            known = {book["key"] for book in ledger["books"]}
            candidates, exclusions, seen = [], [], set()
            for item in inventory:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("name"), str)
                    or not item["name"]
                ):
                    raise LedgerError("Inventory requires a nonempty name")
                key = source_key(item.get("source_path"))
                if key in seen:
                    raise LedgerError("Duplicate source in inventory")
                seen.add(key)
                pages = integer(item.get("pages"), "pages")
                canonical = integer(item.get("canonical_count"), "canonical_count")
                history = integer(item.get("ocr_run_count"), "ocr_run_count")
                reason = (
                    "registered"
                    if key in known
                    else "no_numeric_png"
                    if pages == 0
                    else "canonical_exists"
                    if canonical
                    else "ocr_history_exists"
                    if history
                    else None
                )
                if reason:
                    exclusions.append(
                        {"key": key, "name": item["name"], "reason": reason}
                    )
                else:
                    candidates.append(item)
            selected = sorted(
                candidates, key=lambda item: (item["pages"], item["name"])
            )[:size]
            ledger["last_inventory_exclusions"] = exclusions
            if not selected:
                ledger["run_status"] = "exhausted"
                ledger["run_reason"] = "No eligible unregistered books"
                save(root, ledger, "exhausted", {"exclusions": len(exclusions)})
                return {"created": False, "books": []}
            batch = ledger["next_batch_number"]
            sequence = max(
                (book["global_sequence"] for book in ledger["books"]), default=0
            )
            records = []
            for number, item in enumerate(selected, 1):
                key = source_key(item["source_path"])
                stamp = now()
                book = {
                    "key": key,
                    "name": item["name"],
                    "source_path": posixpath.normpath(item["source_path"]),
                    "pages": item["pages"],
                    "root": str(root / f"batch-{batch:03d}" / f"book-{number:02d}"),
                    "batch_number": batch,
                    "number": number,
                    "global_sequence": sequence + number,
                    "dispatch_token": str(uuid.uuid4()),
                    "title": f"OCR B{batch:03d}-{number:02d} {key[:8]}: {item['name']}",
                    "status": "reserved",
                    "thread_id": None,
                    "host_id": None,
                    "stage_counts": {},
                    "failure_reason": None,
                    "model": "gpt-6.1-sol",
                    "reasoning_effort": "high",
                    "db_reflection": "held",
                    "created_at": stamp,
                    "updated_at": stamp,
                    "source_metadata": item,
                }
                records.append(book)
            ledger["books"].extend(records)
            ledger["batches"].append(
                {
                    "number": batch,
                    "book_keys": [book["key"] for book in records],
                    "created_at": now(),
                }
            )
            ledger["next_batch_number"] += 1
            save(
                root,
                ledger,
                "reserve",
                {"batch_number": batch, "book_keys": [book["key"] for book in records]},
            )
            return {"created": True, "batch_number": batch, "books": records}
        book = next(
            (book for book in ledger["books"] if book["key"] == options.get("key")),
            None,
        )
        if book is None:
            raise LedgerError("Unknown book key")
        if command == "bind":
            thread_id, host_id = options["thread_id"], options.get("host_id", "local")
            if not isinstance(thread_id, str) or not thread_id.strip():
                raise LedgerError("thread_id must be nonempty")
            if book.get("thread_id"):
                if book["thread_id"] != thread_id or book.get("host_id") != host_id:
                    raise LedgerError("Conflicting chat binding")
                return book
            if book["status"] in TERMINAL:
                raise LedgerError("Cannot dispatch a terminal book")
            if any(
                other.get("thread_id") == thread_id and other["key"] != book["key"]
                for other in ledger["books"]
            ):
                raise LedgerError("Chat already assigned to another book")
            book.update(
                thread_id=thread_id,
                host_id=host_id,
                status="dispatched",
                updated_at=now(),
            )
            save(
                root,
                ledger,
                "bind",
                {"key": book["key"], "thread_id": thread_id, "host_id": host_id},
            )
            return book
        if command == "update":
            patch = read_json(Path(options["patch"]))
            if not isinstance(patch, dict) or IMMUTABLE.intersection(patch):
                raise LedgerError("Patch modifies immutable fields or is not an object")
            if book["status"] in TERMINAL:
                raise LedgerError("Terminal book cannot be updated")
            book.update(patch)
            book["updated_at"] = now()
            save(root, ledger, "update", {"key": book["key"], "patch": patch})
            return book
        raise LedgerError(f"Unknown command: {command}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--imports", required=True)
    init.add_argument("--next-batch-number", type=int, default=2)
    reserve = sub.add_parser("reserve")
    reserve.add_argument("--inventory", required=True)
    reserve.add_argument("--size", type=int, default=10)
    bind = sub.add_parser("bind")
    bind.add_argument("--key", required=True)
    bind.add_argument("--thread-id", required=True)
    bind.add_argument("--host-id", default="local")
    update = sub.add_parser("update")
    update.add_argument("--key", required=True)
    update.add_argument("--patch", required=True)
    state = sub.add_parser("state")
    state.add_argument("--status", required=True, choices=sorted(RUN_STATUSES))
    state.add_argument("--reason", required=True)
    sub.add_parser("show")
    args = vars(parser.parse_args())
    root, command = args.pop("root"), args.pop("command")
    try:
        result = operate(root, command, **args)
    except LedgerError as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
