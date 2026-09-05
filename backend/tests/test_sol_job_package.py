from __future__ import annotations

import hashlib
import json
import os
import sqlite3

import pytest

from services.novel_db.sol_job_package import export_input_package


def _database(tmp_path):
    path = tmp_path / "novel.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE books (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY,
            book_id INTEGER,
            page_no INTEGER,
            full_text TEXT,
            index_eligible BOOLEAN
        );
        INSERT INTO books VALUES (1, '対象書籍');
        INSERT INTO pages VALUES (1, 1, 2, '二頁の本文です。根拠として十分な長さがあります。', 1);
        INSERT INTO pages VALUES (2, 1, 3, '三頁の本文です。別の出来事が記録されています。', 1);
        INSERT INTO pages VALUES (3, 1, 4, '', 0);
        """
    )
    connection.commit()
    connection.close()
    return path


def test_export_package_is_content_addressed_and_excludes_old_outputs(tmp_path) -> None:
    database = _database(tmp_path)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    output = tmp_path / "run"

    manifest = export_input_package(
        database_path=database,
        book_name="対象書籍",
        output_dir=output,
        privacy_acknowledged_at="2026-08-23T09:00:00+09:00",
        canonical_names=["人物A"],
        run_id="generation-run-1",
    )

    assert manifest["page_count"] == 2
    assert manifest["page_start"] == 2
    assert manifest["page_end"] == 3
    assert manifest["prompt_version"] == "sol-fact-graph-v1"
    assert manifest["allowed_outputs"] == ["facts"]
    assert manifest["source_sha256"] != manifest["pages_sha256"]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    serialized = (output / "manifest.json").read_text(encoding="utf-8")
    assert str(database) not in serialized
    assert "summary" not in serialized
    pages = [json.loads(line) for line in (output / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [page["page_no"] for page in pages] == [2, 3]
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o700
        assert (output / "manifest.json").stat().st_mode & 0o777 == 0o600
        assert (output / "pages.jsonl").stat().st_mode & 0o777 == 0o600


def test_export_package_rejects_naive_ack_and_input_overflow(tmp_path) -> None:
    database = _database(tmp_path)
    with pytest.raises(ValueError, match="timezone"):
        export_input_package(
            database_path=database,
            book_name="対象書籍",
            output_dir=tmp_path / "naive",
            privacy_acknowledged_at="2026-08-23T09:00:00",
        )

    with pytest.raises(ValueError, match="exceeding"):
        export_input_package(
            database_path=database,
            book_name="対象書籍",
            output_dir=tmp_path / "large",
            privacy_acknowledged_at="2026-08-23T09:00:00+09:00",
            max_input_chars=10,
        )
