from __future__ import annotations

import pytest

from scripts import build_novel_db


def test_page_option_runs_page_level_rebuild(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(build_novel_db, "upgrade_head", lambda: None)
    monkeypatch.setattr(
        build_novel_db,
        "_rebuild_one_page",
        lambda book_name, page_no: not calls.append((book_name, page_no)),
    )

    result = build_novel_db.main(["--book", "test-book", "--page", "42"])

    assert result == 0
    assert calls == [("test-book", 42)]


@pytest.mark.parametrize(
    "args",
    [
        ["--all", "--page", "1"],
        ["--book", "test-book", "--page", "0"],
    ],
)
def test_page_option_requires_book_and_positive_page(args) -> None:
    with pytest.raises(SystemExit, match="2"):
        build_novel_db.main(args)
