"""Reservation and completion failures must never dispatch duplicate books."""

import importlib.util
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "ocr_offline_ledger.py"
spec = importlib.util.spec_from_file_location("ocr_offline_ledger", MODULE_PATH)
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def json_file(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def candidate(name, pages=3, **extra):
    return {
        "name": name,
        "source_path": f"/images/{name}",
        "pages": pages,
        "canonical_count": 0,
        "ocr_run_count": 0,
        **extra,
    }


@pytest.fixture
def run(tmp_path):
    root = tmp_path / "run"
    ledger.operate(root, "init", imports=json_file(tmp_path / "imports.json", []))
    return root


def reserve(root, tmp_path, candidates, **extra):
    return ledger.operate(
        root,
        "reserve",
        inventory=json_file(tmp_path / "inventory.json", candidates),
        **extra,
    )


def update(root, tmp_path, book, patch):
    return ledger.operate(
        root, "update", key=book["key"], patch=json_file(tmp_path / "patch.json", patch)
    )


def test_registered_completed_failed_and_db_history_are_excluded(tmp_path):
    imports = [
        dict(candidate("done"), root="/done", status="completed"),
        dict(
            candidate("failed"),
            root="/failed",
            status="failed",
            failure_reason="Unreadable",
        ),
    ]
    root = tmp_path / "run"
    ledger.operate(root, "init", imports=json_file(tmp_path / "imports.json", imports))
    result = reserve(
        root,
        tmp_path,
        [
            candidate("done"),
            candidate("failed"),
            candidate("canonical", canonical_count=1),
            candidate("history", ocr_run_count=1),
            candidate("large", 9),
            candidate("small", 2),
        ],
    )
    assert [book["name"] for book in result["books"]] == ["small", "large"]
    assert result["batch_number"] == 2
    assert result["books"][0]["global_sequence"] == 3
    assert len(ledger.operate(root, "show")["last_inventory_exclusions"]) == 4


def test_active_batch_is_reused_and_uncertain_dispatch_is_reserved(run, tmp_path):
    inventory = [candidate("one"), candidate("two")]
    first = reserve(run, tmp_path, inventory, size=1)
    update(
        run,
        tmp_path,
        first["books"][0],
        {"status": "dispatch_uncertain", "failure_reason": "Tool response unknown"},
    )
    second = reserve(run, tmp_path, inventory)
    assert second["created"] is False
    assert [book["key"] for book in second["books"]] == [first["books"][0]["key"]]
    assert len(ledger.operate(run, "show")["batches"]) == 1


def test_failed_book_does_not_prevent_next_batch_and_remainder_is_smaller(
    run, tmp_path
):
    candidates = [candidate(str(index)) for index in range(12)]
    first = reserve(run, tmp_path, candidates)
    assert len(first["books"]) == 10
    for book in first["books"]:
        update(
            run,
            tmp_path,
            book,
            {"status": "failed", "failure_reason": "Unrecoverable image"},
        )
    second = reserve(run, tmp_path, candidates)
    assert len(second["books"]) == 2
    assert second["batch_number"] == 3
    assert not (
        {book["key"] for book in first["books"]}
        & {book["key"] for book in second["books"]}
    )


def test_binding_is_idempotent_and_conflicts_fail_without_mutation(run, tmp_path):
    book = reserve(run, tmp_path, [candidate("one")])["books"][0]
    first = ledger.operate(
        run, "bind", key=book["key"], thread_id="chat-1", host_id="local"
    )
    revision = ledger.operate(run, "show")["revision"]
    assert (
        ledger.operate(
            run, "bind", key=book["key"], thread_id="chat-1", host_id="local"
        )
        == first
    )
    with pytest.raises(ledger.LedgerError, match="Conflicting"):
        ledger.operate(
            run, "bind", key=book["key"], thread_id="chat-2", host_id="local"
        )
    assert ledger.operate(run, "show")["revision"] == revision


def test_historical_imports_may_share_manager_chat_but_new_assignments_cannot(tmp_path):
    imports = [
        dict(
            candidate(name),
            root=f"/{name}",
            status="completed",
            thread_id="manager-chat",
            host_id="local",
        )
        for name in ("historic-a", "historic-b")
    ]
    root = tmp_path / "run"
    ledger.operate(root, "init", imports=json_file(tmp_path / "imports.json", imports))
    books = reserve(root, tmp_path, [candidate("new-a"), candidate("new-b")])["books"]
    with pytest.raises(ledger.LedgerError, match="already assigned"):
        ledger.operate(
            root, "bind", key=books[0]["key"], thread_id="manager-chat", host_id="local"
        )
    ledger.operate(
        root, "bind", key=books[0]["key"], thread_id="new-chat", host_id="local"
    )
    with pytest.raises(ledger.LedgerError, match="already assigned"):
        ledger.operate(
            root, "bind", key=books[1]["key"], thread_id="new-chat", host_id="local"
        )
    assert len(ledger.operate(root, "show")["books"]) == 4


def test_unverified_completion_and_immutable_identity_fail_closed(run, tmp_path):
    book = reserve(run, tmp_path, [candidate("one")])["books"][0]
    original = (run / "ledger.json").read_bytes()
    for patch in (
        {"status": "completed"},
        {"root": "/other"},
        {"imported": True},
        {"thread_id": "other"},
        {"status": "failed"},
        {"stage_counts": {"initial": 4}},
    ):
        with pytest.raises(ledger.LedgerError):
            update(run, tmp_path, book, patch)
        assert (run / "ledger.json").read_bytes() == original
    patch = {
        "status": "completed",
        "stage_counts": {
            stage: 3 for stage in ("raw", "review", "evaluation", "final")
        },
        "verification": {"verified": True, "manifest": "/verification.json"},
        "known_unresolved_body": 0,
        "known_unresolved_findings": [],
        "db_reflection": "held",
    }
    assert update(run, tmp_path, book, patch)["status"] == "completed"


@pytest.mark.parametrize("status", ["quota_stop", "user_stopped", "exhausted"])
def test_stopped_run_cannot_reserve(run, tmp_path, status):
    ledger.operate(run, "state", status=status, reason="stop")
    with pytest.raises(ledger.LedgerError, match="stopped"):
        reserve(run, tmp_path, [candidate("one")])


def test_corruption_duplicate_inventory_and_duplicate_imports_fail_closed(
    run, tmp_path
):
    before = (run / "ledger.json").read_bytes()
    with pytest.raises(ledger.LedgerError, match="Duplicate source"):
        reserve(run, tmp_path, [candidate("one"), candidate("one")])
    assert (run / "ledger.json").read_bytes() == before
    data = json.loads(before)
    data["run_status"] = "typo"
    (run / "ledger.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="Invalid run status"):
        ledger.operate(run, "show")
    assert json.loads((run / "ledger.json").read_text())["run_status"] == "typo"
    record = dict(candidate("one"), root="/one", status="completed")
    with pytest.raises(ledger.LedgerError, match="Duplicate"):
        ledger.operate(
            tmp_path / "duplicate",
            "init",
            imports=json_file(tmp_path / "imports.json", [record, record]),
        )
    assert not (tmp_path / "duplicate" / "ledger.json").exists()


def test_projection_recovery_retains_authoritative_events(run, tmp_path):
    reserve(run, tmp_path, [candidate("one")])
    (run / "events.jsonl").write_text("truncated", encoding="utf-8")
    (run / "LEDGER.md").unlink()
    result = ledger.operate(run, "show")
    assert [
        json.loads(line) for line in (run / "events.jsonl").read_text().splitlines()
    ] == result["events"]
    assert "one" in (run / "LEDGER.md").read_text()


def test_markdown_quality_and_selected_artifacts_are_readable(run, tmp_path):
    book = reserve(run, tmp_path, [candidate("one")])["books"][0]
    update(
        run,
        tmp_path,
        book,
        {
            "known_unresolved_body": [],
            "known_unresolved_findings": 0,
            "nonbody_holds": ["cover crop"],
            "artifacts": {
                "report": "/some path/report.md",
                "body_text": "final/body.txt",
                "bundle": {"path": "final/bundle.json"},
                "private_detail": "JSON only",
            },
        },
    )
    text = (run / "LEDGER.md").read_text()
    assert "未解決本文" in text and "非本文保留" in text
    assert f"[保存先](<{book['root']}>)" in text
    assert "[report](</some path/report.md>)" in text
    assert f"[body](<{book['root']}/final/body.txt>)" in text
    assert f"[bundle](<{book['root']}/final/bundle.json>)" in text
    assert "JSON only" not in text


def test_failed_atomic_replace_preserves_original_ledger(run, tmp_path, monkeypatch):
    original = (run / "ledger.json").read_bytes()

    def reject_replace(source, target):
        raise OSError("Simulated disk error before replace")

    monkeypatch.setattr(ledger.os, "replace", reject_replace)
    with pytest.raises(OSError, match="Simulated disk error"):
        reserve(run, tmp_path, [candidate("one")])
    assert (run / "ledger.json").read_bytes() == original
    assert not list(run.glob(".ledger.json.*"))


def test_normalized_source_identity_cannot_be_reserved_twice(run, tmp_path):
    first = candidate("one", source_path="/images/./one")
    second = candidate("alias", source_path="/images/one")
    with pytest.raises(ledger.LedgerError, match="Duplicate source"):
        reserve(run, tmp_path, [first, second])
    assert not ledger.operate(run, "show")["books"]


@pytest.mark.parametrize(
    "override",
    [
        {"known_unresolved_body": True},
        {"known_unresolved_findings": ["unfixed"]},
        {"verification": {"verified": "true"}},
        {"db_reflection": "published"},
        {"stage_counts": {"raw": 3, "review": 3, "evaluation": 2, "final": 3}},
    ],
)
def test_completion_quality_gate_cannot_be_bypassed(run, tmp_path, override):
    book = reserve(run, tmp_path, [candidate("one")])["books"][0]
    original = (run / "ledger.json").read_bytes()
    patch = {
        "status": "completed",
        "stage_counts": {
            stage: 3 for stage in ("raw", "review", "evaluation", "final")
        },
        "verification": {"verified": True},
        "known_unresolved_body": 0,
        "known_unresolved_findings": [],
        "db_reflection": "held",
        **override,
    }
    with pytest.raises(ledger.LedgerError):
        update(run, tmp_path, book, patch)
    assert (run / "ledger.json").read_bytes() == original


def _concurrent_reserve(args):
    module_spec = importlib.util.spec_from_file_location("worker_ledger", MODULE_PATH)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module.operate(Path(args[0]), "reserve", inventory=args[1])


def test_concurrent_reservation_cannot_create_two_batches(run, tmp_path):
    inventory = json_file(
        tmp_path / "inventory.json", [candidate(str(index)) for index in range(15)]
    )
    with ProcessPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_concurrent_reserve, [(str(run), inventory)] * 2))
    assert sum(result["created"] for result in results) == 1
    assert {book["key"] for book in results[0]["books"]} == {
        book["key"] for book in results[1]["books"]
    }
    assert len(ledger.operate(run, "show")["books"]) == 10
