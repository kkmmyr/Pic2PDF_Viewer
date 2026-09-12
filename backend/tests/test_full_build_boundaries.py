"""Full Buildの検査・保存moduleへ具体runtimeが再流入しないことを検査する。"""

from pathlib import Path

import pytest

from tests.test_quality_guardrails import import_boundaries


@pytest.mark.parametrize(
    ("module", "source", "rejected"),
    [
        ("full_build_content", "import sqlite3", True),
        ("full_build_content", "from ..summarizer import summarize_book_with_characters", True),
        ("full_build_content", "from .. import summary_index", True),
        ("full_build_content", "from config import app_settings", True),
        ("full_build_content", "from fastapi import HTTPException", True),
        ("full_build_content", "from ..character_names import normalize_character_entries", False),
        ("full_build_content", "from services.novel_db import character_names", False),
        ("full_build_content", "from dataclasses import dataclass", False),
        ("full_build_repository", "from ..full_builder import build_book_full", True),
        ("full_build_repository", "from services.novel_db import connection", True),
        ("full_build_repository", "import backend.services.novel_db.summary_index", True),
        ("full_build_repository", "import lancedb", True),
        ("full_build_repository", "import sqlite3", False),
        ("full_build_repository", "from .full_build_content import CharacterRow", False),
    ],
)
def test_full_build_dependency_boundary(tmp_path: Path, module: str, source: str, rejected: bool) -> None:
    path = tmp_path / "backend" / "services" / "novel_db" / "generation" / f"{module}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source + "\n", encoding="utf-8")
    violations = import_boundaries.find_violations(tmp_path, require_novel_targets=False)
    assert bool(violations) is rejected
    if rejected:
        assert all("Full Build boundary" in violation for violation in violations)
