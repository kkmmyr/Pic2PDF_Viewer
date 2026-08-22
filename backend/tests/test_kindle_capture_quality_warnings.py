"""Kindle capture品質warningの監査世代・確認状態テスト。"""

from datetime import UTC, datetime

import pytest

from services.kindle_catalog.capture_quality_warnings import (
    list_warnings,
    set_read,
)
from services.kindle_catalog.capture_registration_repository import mark_succeeded
from services.kindle_catalog.connection import with_db
from services.kindle_catalog.migrations import upgrade_head


def _audit(*, digest: str = "a" * 64, warnings: list[dict] | None = None) -> dict:
    return {
        "qa_policy_version": "kindle-image-qa-v1",
        "warning_policy_version": "kindle-image-warning-v1",
        "quality_sha256": digest,
        "warnings": warnings or [],
    }


def _warning(code: str = "blank_or_sparse_candidate") -> dict:
    finding = {
        "code": code,
        "severity": "warning",
        "files": ["001.png", "003.png"],
        "metrics": {"mean_luma": 255.0},
    }
    return {
        "code": code,
        "finding_count": 1,
        "files": ["001.png", "003.png"],
        "findings": [finding],
    }


def _seed_job(job_id: str, *, status: str = "awaiting_files") -> None:
    with with_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO books(
                asin,title,title_normalized,category,book_type
            ) VALUES ('B000QUALITY','品質確認作品','品質確認作品','kindle','comic')
            """
        )
        conn.execute(
            """
            INSERT INTO capture_jobs(
                id,asin,source,status,direction,requested_at,agent_id
            ) VALUES (?,'B000QUALITY','comic',?,'left',
                      '2026-08-22T10:00:00+09:00','windows-1')
            """,
            (job_id, status),
        )


def _succeed(job_id: str, audit: dict) -> None:
    mark_succeeded(
        job_id,
        "windows-1",
        completed_at=datetime(2026, 8, 22, 1, 0, tzinfo=UTC),
        book_id="品質確認作品",
        captured_screens=3,
        quality_audit=audit,
    )


def test_warning_is_persisted_and_read_state_can_round_trip(tmp_data_dir) -> None:
    upgrade_head()
    _seed_job("job-1")
    _succeed("job-1", _audit(warnings=[_warning()]))

    unread = list_warnings()

    assert unread["total"] == 1
    assert unread["unread_count"] == 1
    assert unread["read_count"] == 0
    item = unread["items"][0]
    assert item["title"] == "品質確認作品"
    assert item["book_id"] == "品質確認作品"
    assert item["pages"] == [1, 3]
    assert item["finding_count"] == 1
    assert item["is_read"] is False

    fixed = datetime(2026, 8, 22, 2, 30, tzinfo=UTC)
    updated = set_read(item["id"], True, now=fixed)

    assert updated["is_read"] is True
    assert updated["read_at"] == fixed.isoformat()
    assert list_warnings("unread")["total"] == 0
    assert list_warnings("read")["total"] == 1

    restored = set_read(item["id"], False, now=fixed)
    assert restored["is_read"] is False
    assert restored["read_at"] is None


def test_zero_warning_generation_supersedes_old_candidates(tmp_data_dir) -> None:
    upgrade_head()
    _seed_job("job-1")
    _succeed("job-1", _audit(warnings=[_warning()]))
    old_warning_id = list_warnings()["items"][0]["id"]

    _seed_job("job-2")
    _succeed("job-2", _audit(digest="b" * 64))

    assert list_warnings("all") == {
        "items": [],
        "total": 0,
        "unread_count": 0,
        "read_count": 0,
    }
    with pytest.raises(ValueError, match="有効な品質warning"):
        set_read(old_warning_id, True)
    with with_db() as conn:
        audits = conn.execute(
            """
            SELECT job_id,superseded_at,superseded_by_job_id
            FROM capture_quality_audits ORDER BY id
            """
        ).fetchall()
    assert audits[0]["job_id"] == "job-1"
    assert audits[0]["superseded_at"] is not None
    assert audits[0]["superseded_by_job_id"] == "job-2"
    assert audits[1]["job_id"] == "job-2"
    assert audits[1]["superseded_at"] is None


def test_audit_failure_rolls_back_capture_job_update(tmp_data_dir) -> None:
    upgrade_head()
    _seed_job("job-rollback")
    invalid_warning = _warning()
    invalid_warning["files"] = [{"not": {"json-serializable"}}]

    with pytest.raises(TypeError):
        _succeed("job-rollback", _audit(warnings=[invalid_warning]))

    with with_db() as conn:
        job = conn.execute("SELECT status,book_id FROM capture_jobs WHERE id='job-rollback'").fetchone()
        audit_count = conn.execute("SELECT COUNT(*) FROM capture_quality_audits").fetchone()[0]
    assert job["status"] == "awaiting_files"
    assert job["book_id"] is None
    assert audit_count == 0


def test_warning_api_lists_and_updates_active_candidate(client) -> None:
    upgrade_head()
    _seed_job("job-api")
    _succeed("job-api", _audit(warnings=[_warning("low_size_candidate")]))

    response = client.get("/api/kindle-catalog/capture-quality-warnings")

    assert response.status_code == 200
    body = response.json()
    assert body["unread_count"] == 1
    assert body["items"][0]["code"] == "low_size_candidate"

    warning_id = body["items"][0]["id"]
    update = client.patch(
        f"/api/kindle-catalog/capture-quality-warnings/{warning_id}",
        json={"is_read": True},
    )

    assert update.status_code == 200
    assert update.json()["is_read"] is True
    assert client.get("/api/kindle-catalog/capture-quality-warnings?status=read").json()["total"] == 1


def test_warning_api_rejects_unknown_or_inactive_candidate(client) -> None:
    upgrade_head()

    response = client.patch(
        "/api/kindle-catalog/capture-quality-warnings/999",
        json={"is_read": True},
    )

    assert response.status_code == 404
