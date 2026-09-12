"""Library保存adapterだけに許可した依存と撮影側の逆依存を検査する。"""

from pathlib import Path

import pytest

from tests.test_quality_guardrails import import_boundaries


@pytest.mark.parametrize(
    ("module", "source", "rejected"),
    [
        ("library/capture_metadata", "from services.meta_store import update_meta_locked", False),
        ("library/capture_metadata", "from .. import meta_store", False),
        ("library/capture_metadata", "import backend.services.meta_store", False),
        ("library/capture_metadata", "from services.meta_db import db_connection", True),
        ("library/capture_metadata", "from .. import meta_db", True),
        ("library/capture_metadata", "from services.kindle_catalog import capture_jobs", True),
        ("library/capture_metadata", "import config", True),
        ("library/capture_metadata", "import fastapi", True),
        ("library/capture_metadata", "import sqlite3", True),
        ("library/capture_metadata", "import sqlalchemy", True),
        ("library/image_listing", "from services.meta_store import load_meta", True),
        ("library/other", "from .. import meta_store", True),
        ("library/__init__", "import services.meta_store", True),
        ("kindle_catalog/capture_publication", "from services.meta_store import load_meta", True),
        ("kindle_catalog/capture_publication", "from .. import meta_store", True),
        ("kindle_catalog/capture_publication", "import backend.services.meta_db", True),
        (
            "kindle_catalog/capture_publication",
            "from services.library.capture_metadata import CaptureMetadataChange",
            False,
        ),
    ],
)
def test_capture_metadata_dependency_scope(tmp_path: Path, module: str, source: str, rejected: bool) -> None:
    path = tmp_path / "backend/services" / f"{module}.py"
    path.parent.mkdir(parents=True)
    path.write_text(source + "\n", encoding="utf-8")

    assert bool(import_boundaries.find_violations(tmp_path, require_novel_targets=False)) is rejected
