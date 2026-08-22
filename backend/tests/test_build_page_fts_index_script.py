from __future__ import annotations

import json
from contextlib import nullcontext

from scripts import build_page_fts_index
from services.novel_db.page_fts import PageFtsBuildResult


def test_cli_prints_manifest_without_page_text(monkeypatch, capsys) -> None:
    result = PageFtsBuildResult(
        table_name="pages_icu_r0_0123456789ab_1",
        source_revision=0,
        row_count=3,
        source_sha256="a" * 64,
        built_at="2026-08-22 12:00:00",
        lancedb_version="0.34.0",
    )
    monkeypatch.setattr(build_page_fts_index, "upgrade_head", lambda: None)
    monkeypatch.setattr(build_page_fts_index, "with_db", lambda: nullcontext(object()))
    monkeypatch.setattr(build_page_fts_index, "build_page_fts_index", lambda _conn: result)

    assert build_page_fts_index.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, **result.to_dict()}
    assert "text" not in payload
