from datetime import UTC, datetime

import config
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.import_run_lifecycle import (
    fail_import_run,
    finish_import_run,
    start_import_run,
)
from services.kindle_catalog.migrations import upgrade_head


def test_import_run_lifecycle_records_success_metrics(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path / "target"))
    fixed = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(
        "services.kindle_catalog.import_run_lifecycle.jst_now",
        lambda: fixed,
    )
    upgrade_head()

    run_id = start_import_run("kindle_info")
    finish_import_run(
        run_id,
        status="succeeded",
        files=2,
        records=10,
        skipped=3,
    )

    with with_db() as conn:
        row = conn.execute("SELECT * FROM import_runs WHERE id=?", (run_id,)).fetchone()
    assert row["source_kind"] == "kindle_info"
    assert row["status"] == "succeeded"
    assert row["started_at"] == fixed.isoformat()
    assert row["finished_at"] == fixed.isoformat()
    assert row["files_processed"] == 2
    assert row["records_processed"] == 10
    assert row["records_skipped"] == 3
    assert row["error_message"] is None


def test_import_run_lifecycle_records_failure_without_masking_message(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path / "target"))
    upgrade_head()

    run_id = start_import_run("amazon_orders")
    fail_import_run(run_id, RuntimeError("broken csv"))

    with with_db() as conn:
        row = conn.execute("SELECT * FROM import_runs WHERE id=?", (run_id,)).fetchone()
    assert row["status"] == "failed"
    assert row["finished_at"] is not None
    assert row["files_processed"] == 0
    assert row["records_processed"] == 0
    assert row["records_skipped"] == 0
    assert row["error_message"] == "broken csv"
