"""Exercise the new boundaries with disposable source trees, before moving code."""

from pathlib import Path

import pytest

from tests.test_quality_guardrails import import_boundaries


@pytest.mark.parametrize(
    ("path", "source", "rejected"),
    [
        ("bootstrap/runtime.py", "from services.meta_db import init_db", True),
        ("bootstrap/runtime.py", "from backend import main", True),
        ("bootstrap/runtime.py", "from ..services import meta_db", True),
        ("bootstrap/runtime.py", "import config", True),
        ("bootstrap/runtime.py", "from fastapi import FastAPI", True),
        ("bootstrap/runtime.py", "from collections.abc import Callable", False),
        ("services/library/image_listing.py", "from backend import routers", True),
        ("services/library/image_listing.py", "from .. import novel_db", True),
        ("services/library/image_listing.py", "from ...bootstrap import runtime", True),
        ("services/library/image_listing.py", "import services.meta_db", True),
        ("services/library/image_listing.py", "from config import get_dirs_by_source", True),
        ("services/library/image_listing.py", "from starlette.exceptions import HTTPException", True),
        ("services/library/__init__.py", "from .image_listing import BookImageFile", False),
        ("services/library/image_listing.py", "from services.library.types import Item", False),
        ("services/library/image_listing.py", "from utils.path_utils import join_path", False),
    ],
)
def test_isolated_backend_import_boundaries(tmp_path: Path, path: str, source: str, rejected: bool) -> None:
    target = tmp_path / "backend" / path
    target.parent.mkdir(parents=True)
    target.write_text(source + "\n", encoding="utf-8")
    violations = import_boundaries.find_violations(tmp_path)
    assert bool(violations) is rejected
    if rejected:
        assert any("isolated backend module" in violation for violation in violations)
