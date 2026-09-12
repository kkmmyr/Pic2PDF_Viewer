"""A relocation must not silently remove a reviewed Novel dependency boundary."""

from pathlib import Path

import pytest

from tests.test_quality_guardrails import import_boundaries

TARGETS = (
    "full_build_content",
    "full_build_repository",
    "search_ranking",
    "search_presentation",
    "search_queries",
    "ocr_job_application",
)


@pytest.fixture
def boundary_tree(tmp_path: Path) -> Path:
    root = tmp_path / "backend/services/novel_db"
    root.mkdir(parents=True)
    for name in TARGETS:
        (root / f"{name}.py").write_text("from __future__ import annotations\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("name", TARGETS)
@pytest.mark.parametrize("move", [False, True], ids=["deleted", "unregistered-move"])
def test_required_boundary_cannot_disappear(boundary_tree: Path, name: str, move: bool) -> None:
    path = boundary_tree / "backend/services/novel_db" / f"{name}.py"
    if move:
        destination = path.parent / "nested" / path.name
        destination.parent.mkdir()
        path.rename(destination)
    else:
        path.unlink()

    errors = import_boundaries.find_violations(boundary_tree)

    assert len(errors) == 1
    assert f"{name}.py: required Novel boundary target is missing" in errors[0]


@pytest.mark.parametrize(
    ("source", "valid"),
    [
        ("from collections.abc import Sequence", True),
        ("import sqlite3", False),
        ("from ..embedder import embed_batch", False),
        ("from .. import embedder", False),
        ("import backend.services.novel_db.embedder", False),
    ],
)
def test_registered_relocation_still_checks_imports(
    boundary_tree: Path, monkeypatch: pytest.MonkeyPatch, source: str, valid: bool
) -> None:
    root = boundary_tree / "backend/services/novel_db"
    moved = root / "retrieval/search_ranking.py"
    moved.parent.mkdir()
    (root / "search_ranking.py").rename(moved)
    moved.write_text(source + "\n", encoding="utf-8")
    monkeypatch.setitem(import_boundaries.NOVEL_MODULE_PATHS, "search_ranking", "retrieval/search_ranking.py")

    errors = import_boundaries.find_violations(boundary_tree)

    assert bool(errors) is not valid
    assert all("retrieval/search_ranking.py:" in error and "Search boundary imports" in error for error in errors)


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_boundary_registration_cannot_omit_or_reuse_target(
    boundary_tree: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    if mutation == "missing":
        monkeypatch.delitem(import_boundaries.NOVEL_MODULE_PATHS, "search_queries")
    else:
        monkeypatch.setitem(import_boundaries.NOVEL_MODULE_PATHS, "search_queries", "search_ranking.py")

    errors = import_boundaries.find_violations(boundary_tree)

    assert len(errors) == 1
    assert "Novel boundary target registration" in errors[0]


def test_partial_fixture_opt_out_keeps_present_module_checks(tmp_path: Path) -> None:
    path = tmp_path / "backend/services/novel_db/search_ranking.py"
    path.parent.mkdir(parents=True)
    path.write_text("import sqlite3\n", encoding="utf-8")

    errors = import_boundaries.find_violations(tmp_path, require_novel_targets=False)

    assert errors == ["backend/services/novel_db/search_ranking.py:1: Search boundary imports sqlite3"]


@pytest.mark.parametrize("missing", [False, True])
def test_cli_requires_all_boundary_targets(
    boundary_tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], missing: bool
) -> None:
    if missing:
        (boundary_tree / "backend/services/novel_db/search_ranking.py").unlink()
    find_violations = import_boundaries.find_violations
    monkeypatch.setattr(import_boundaries, "find_violations", lambda: find_violations(boundary_tree))

    assert import_boundaries.main() == int(missing)
    output = capsys.readouterr().out
    assert ("required Novel boundary target is missing" in output) is missing


def test_current_repository_retains_all_reviewed_boundaries() -> None:
    assert set(import_boundaries.NOVEL_MODULE_PATHS) == set(TARGETS)
    assert import_boundaries.find_violations() == []
