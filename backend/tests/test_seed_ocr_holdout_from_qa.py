from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "seed_ocr_holdout_from_qa.py"
_SPEC = importlib.util.spec_from_file_location("seed_ocr_holdout", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
seed = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seed)


def _valid_page(**overrides) -> dict:
    page = {
        "page_no": 1,
        "qa_state": "approved",
        "page_type": "narrative",
        "layout_type": "normal_prose",
        "selected_engine": "codex",
        "corrected_text": "verified text",
    }
    page.update(overrides)
    return page


def test_validate_holdout_page_accepts_preapproved_codex_correction() -> None:
    seed.validate_holdout_page(_valid_page())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("qa_state", "required"),
        ("page_type", "toc"),
        ("layout_type", "mixed_illustration"),
        ("selected_engine", "primary"),
        ("corrected_text", ""),
    ],
)
def test_validate_holdout_page_rejects_unverified_sources(field: str, value: str) -> None:
    page = _valid_page()
    page[field] = value

    with pytest.raises(ValueError):
        seed.validate_holdout_page(page)


def test_build_run_selection_keeps_only_eligible_pages() -> None:
    result = seed.build_run_selection(
        {
            30: {
                "book_name": "book-a",
                "pages": [_valid_page(), _valid_page(page_type="illustration")],
            },
            49: {"book_name": "book-b", "pages": [_valid_page()]},
        }
    )

    assert [(item["run_id"], item["series"]) for item in result["entries"]] == [
        (30, "book-a"),
        (49, "book-b"),
    ]
