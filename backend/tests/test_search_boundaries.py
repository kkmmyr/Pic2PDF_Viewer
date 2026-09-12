"""検索候補取得・順位・整形の静的依存境界を固定する。"""

from pathlib import Path

import pytest

from tests.test_quality_guardrails import import_boundaries


@pytest.mark.parametrize(
    ("module", "source", "rejected"),
    [
        ("search_ranking", "import sqlite3", True),
        ("search_ranking", "from . import search_presentation", True),
        ("search_ranking", "from config import novel_db", True),
        ("search_ranking", "from collections.abc import Sequence", False),
        ("search_presentation", "from .search import SearchHit", True),
        ("search_presentation", "from .search_queries import query_fts_rows", True),
        ("search_presentation", "import fastapi", True),
        ("search_presentation", "from .search_ranking import RankedPage", False),
        ("search_presentation", "from urllib.parse import quote", False),
        ("search_queries", "from .embedder import embed_batch", True),
        ("search_queries", "from .lance_store import get_chunks_table", True),
        ("search_queries", "import backend.services.novel_db.search", True),
        ("search_queries", "from lancedb.table import Table", False),
        ("search_queries", "import sqlite3", False),
    ],
)
def test_search_dependency_boundary(tmp_path: Path, module: str, source: str, rejected: bool) -> None:
    path = tmp_path / "backend" / "services" / "novel_db" / f"{module}.py"
    path.parent.mkdir(parents=True)
    path.write_text(source + "\n", encoding="utf-8")
    violations = import_boundaries.find_violations(tmp_path, require_novel_targets=False)
    assert bool(violations) is rejected
    if rejected:
        assert all("Search boundary" in violation for violation in violations)


def test_public_search_types_and_snippet_imports_are_preserved():
    from services.novel_db import SearchHit as package_hit
    from services.novel_db import search, search_presentation

    assert search.SearchHit is package_hit is search_presentation.SearchHit
    assert search.sanitize_snippet is search_presentation.sanitize_snippet
