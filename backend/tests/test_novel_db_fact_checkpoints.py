"""Fact extraction structure, validation, and checkpoint reuse tests."""

from __future__ import annotations

import json

import pytest

from services.novel_db import with_db
from services.novel_db.fact_checkpoints import (
    FACT_EXTRACTION_SCHEMA_VERSION,
    hash_source_pages,
    load_fact_block,
    prune_fact_blocks,
    save_fact_block,
    validate_and_structure_fact_sheet,
)
from services.novel_db.generation_quality import BookFactSheet
from services.novel_db.migrations import upgrade_head


@pytest.fixture
def book_id(tmp_data_dir) -> int:
    upgrade_head()
    with with_db() as conn:
        cursor = conn.execute(
            "INSERT INTO books (name, pdf_path, images_dir, page_count) VALUES (?, ?, ?, ?)",
            ("fact-book", "/fact.pdf", "/images", 3),
        )
        conn.commit()
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)


def _sheet() -> BookFactSheet:
    return BookFactSheet(
        book_facts=("- [page 1] 茉莉花が課題を引き受けた。\n- [page 2] 茉莉花が手掛かりを得た結果、調査が進んだ。"),
        character_facts={"茉莉花": "- [page 1] 課題を引き受けた。\n- [page 2] 調査を進めた。"},
    )


def test_validate_and_structure_fact_sheet_keeps_pages_and_character() -> None:
    records = validate_and_structure_fact_sheet(_sheet(), allowed_pages={1, 2})

    assert [record.pages for record in records] == [(1,), (2,), (1,), (2,)]
    assert records[0].kind == "book"
    assert records[2].character_name == "茉莉花"
    assert records[0].text == "茉莉花が課題を引き受けた。"


def test_validate_rejects_fact_without_page_evidence() -> None:
    sheet = BookFactSheet(
        book_facts="- 茉莉花が課題を引き受けた。",
        character_facts={"茉莉花": "- [page 1] 課題を引き受けた。"},
    )

    with pytest.raises(ValueError, match="missing page evidence"):
        validate_and_structure_fact_sheet(sheet, allowed_pages={1})


def test_validate_rejects_page_outside_source_block() -> None:
    sheet = BookFactSheet(
        book_facts="- [page 99] 茉莉花が課題を引き受けた。",
        character_facts={"茉莉花": "- [page 1] 課題を引き受けた。"},
    )

    with pytest.raises(ValueError, match="outside its block: 99"):
        validate_and_structure_fact_sheet(sheet, allowed_pages={1, 2})


def test_validate_accepts_grouped_page_evidence_and_checks_every_page() -> None:
    sheet = BookFactSheet(
        book_facts="- [page 18, page 20] 影傑が茉莉花を出迎えた。",
        character_facts={"影傑": "- [page 18、20] 茉莉花と面会した。"},
    )

    records = validate_and_structure_fact_sheet(sheet, allowed_pages={18, 20})

    assert [record.pages for record in records] == [(18, 20), (18, 20)]
    assert records[0].text == "影傑が茉莉花を出迎えた。"


def test_validate_rejects_invalid_page_inside_grouped_evidence() -> None:
    sheet = BookFactSheet(
        book_facts="- [page 18, page 99] 影傑が茉莉花を出迎えた。",
        character_facts={"影傑": "- [page 18] 茉莉花と面会した。"},
    )

    with pytest.raises(ValueError, match="outside its block: 99"):
        validate_and_structure_fact_sheet(sheet, allowed_pages={18, 20})


def test_checkpoint_roundtrip_and_identity(book_id: int) -> None:
    pages = [(1, "第一ページ"), (2, "第二ページ")]
    source_hash = hash_source_pages(pages)
    records = validate_and_structure_fact_sheet(_sheet(), allowed_pages={1, 2})

    with with_db() as conn:
        save_fact_block(
            conn,
            book_id=book_id,
            block_index=1,
            pages=pages,
            source_hash=source_hash,
            model="writer-model",
            sheet=_sheet(),
            records=records,
        )
        loaded = load_fact_block(
            conn,
            book_id=book_id,
            block_index=1,
            source_hash=source_hash,
            model="writer-model",
        )
        wrong_model = load_fact_block(
            conn,
            book_id=book_id,
            block_index=1,
            source_hash=source_hash,
            model="other-model",
        )
        row = conn.execute(
            "SELECT schema_version, fact_records_json FROM fact_extraction_blocks WHERE book_id = ?",
            (book_id,),
        ).fetchone()

    assert loaded == _sheet()
    assert wrong_model is None
    assert row is not None
    assert row[0] == FACT_EXTRACTION_SCHEMA_VERSION
    payload = json.loads(row[1])
    assert payload[0] == {
        "character_name": None,
        "kind": "book",
        "pages": [1],
        "text": "茉莉花が課題を引き受けた。",
    }


def test_source_hash_changes_when_character_ledger_changes() -> None:
    pages = [(1, "第一ページ")]

    assert hash_source_pages(pages, prompt_context="- 皓茉莉花") != hash_source_pages(
        pages,
        prompt_context="- 茉莉花",
    )


def test_prune_removes_only_obsolete_tail_blocks(book_id: int) -> None:
    pages = [(1, "第一ページ"), (2, "第二ページ")]
    records = validate_and_structure_fact_sheet(_sheet(), allowed_pages={1, 2})
    with with_db() as conn:
        for block_index in (1, 2):
            save_fact_block(
                conn,
                book_id=book_id,
                block_index=block_index,
                pages=pages,
                source_hash=f"hash-{block_index}",
                model="writer-model",
                sheet=_sheet(),
                records=records,
            )
        prune_fact_blocks(conn, book_id=book_id, block_count=1)
        remaining = conn.execute(
            "SELECT block_index FROM fact_extraction_blocks WHERE book_id = ?",
            (book_id,),
        ).fetchall()

    assert [row[0] for row in remaining] == [1]
