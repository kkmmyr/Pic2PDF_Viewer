from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "audit_ocr_finetune_corpus.py"
_SPEC = importlib.util.spec_from_file_location("audit_ocr_finetune_corpus", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


def _page(**overrides: object) -> dict:
    page = {
        "qa_state": "approved",
        "page_type": "narrative",
        "layout_type": "normal_prose",
        "selected_engine": "codex",
        "corrected_text": "正しい 本文",
    }
    page.update(overrides)
    return page


def _run(run_id: int, pages: list[dict], **overrides: object) -> dict:
    run = {
        "id": run_id,
        "book_name": f"book-{run_id}",
        "state": "completed",
        "qa_state": "approved",
        "pages": pages,
    }
    run.update(overrides)
    return run


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("qa_state", "pending"),
        ("page_type", "toc"),
        ("layout_type", "mixed_illustration"),
        ("selected_engine", "primary"),
        ("corrected_text", ""),
    ],
)
def test_is_eligible_page_rejects_non_training_pages(field: str, value: str) -> None:
    assert not audit.is_eligible_page(_page(**{field: value}))


def test_build_inventory_isolates_entire_holdout_runs_without_text() -> None:
    result = audit.build_inventory(
        [
            _run(1, [_page(), _page(corrected_text="四文字")]),
            _run(2, [_page(corrected_text="予約本文")]),
            _run(3, [_page()], qa_state="pending"),
        ],
        holdout_run_ids={2},
    )

    assert result["training"]["run_count"] == 1
    assert result["training"]["eligible_pages"] == 2
    assert result["holdout"]["run_count"] == 1
    assert result["holdout"]["runs"][0]["run_id"] == 2
    assert result["contains_page_text"] is False
    assert "正しい本文" not in str(result)
    assert "予約本文" not in str(result)


def test_build_inventory_fails_closed_when_holdout_is_unavailable() -> None:
    with pytest.raises(ValueError, match="no eligible pages"):
        audit.build_inventory([_run(1, [_page()])], holdout_run_ids={99})
