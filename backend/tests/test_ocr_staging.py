from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from services.novel_db.connection import with_db
from services.novel_db.extractor import OcrPageResult
from services.novel_db.migrations import upgrade_head
from services.novel_db.ocr_page_classification import classify_run_pages as classification_classify_run_pages
from services.novel_db.ocr_page_types import suggest_page_type
from services.novel_db.ocr_qa import stage_run_for_qa as qa_stage_run_for_qa
from services.novel_db.ocr_qa_risk import detect_qa_risk_flags
from services.novel_db.ocr_run_store import collect_input_pages as store_collect_input_pages
from services.novel_db.ocr_staging import (
    approve_and_publish_run,
    classify_run_pages,
    collect_input_pages,
    prepare_run,
    review_qa_page,
    save_page_result,
    stage_run_for_qa,
)


def test_facade_preserves_public_symbol_identity() -> None:
    assert collect_input_pages is store_collect_input_pages
    assert classify_run_pages is classification_classify_run_pages
    assert stage_run_for_qa is qa_stage_run_for_qa


@pytest.fixture
def staged_book(tmp_data_dir) -> tuple[str, list]:
    upgrade_head()
    book_name = "surya-test-book"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    Image.new("RGB", (100, 140), "white").save(images_dir / "001.png")
    Image.new("RGB", (100, 140), "white").save(images_dir / "002.png")
    return book_name, collect_input_pages(book_name)


def _passed_page(page_no: int, image_sha256: str, text: str) -> OcrPageResult:
    return {
        "page_no": page_no,
        "image_sha256": image_sha256,
        "state": "passed",
        "full_text": text,
        "char_count": len(text),
        "raw_output": f'<div data-label="Text" data-bbox="0 0 1000 1000">{text}</div>',
        "block_count": 1,
        "quality_flags": [],
        "ink_coverage": 1.0,
        "attempt_count": 1,
        "error_message": None,
        "layout_type": "normal_prose",
        "primary_text": text,
        "external_text": None,
        "selected_engine": "primary",
    }


def test_run_resumes_then_requires_qa_before_publication(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, tasks = prepare_run(book_name, "surya2", "model-sha", input_pages)
    assert [task["page_no"] for task in tasks] == [1, 2]

    save_page_result(run_id, _passed_page(1, input_pages[0].image_sha256, "一頁目"))
    with pytest.raises(ValueError, match="incomplete"):
        stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0

    resumed_run_id, remaining = prepare_run(book_name, "surya2", "model-sha", input_pages)
    assert resumed_run_id == run_id
    assert [task["page_no"] for task in remaining] == [2]

    save_page_result(run_id, _passed_page(2, input_pages[1].image_sha256, "二頁目"))
    stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
        assert conn.execute("SELECT state FROM ocr_runs WHERE id=?", (run_id,)).fetchone()[0] == "awaiting_qa"
        required = conn.execute(
            "SELECT page_no FROM ocr_page_results WHERE run_id=? AND qa_state='required' ORDER BY page_no",
            (run_id,),
        ).fetchall()
        assert [row[0] for row in required] == [1, 2]

    review_qa_page(run_id, 1, "approved", None, "narrative", "normal_prose", "primary", None)
    review_qa_page(
        run_id,
        2,
        "approved",
        "確認済み",
        "narrative",
        "normal_prose",
        "primary",
        None,
    )
    approve_and_publish_run(run_id, "tester")

    with with_db() as conn:
        book = conn.execute("SELECT id, page_count, ocr_done_at FROM books WHERE name=?", (book_name,)).fetchone()
        assert (book[1], book[2] is not None) == (2, True)
        pages = conn.execute(
            "SELECT page_no, full_text, page_type, index_eligible FROM pages WHERE book_id=? ORDER BY page_no",
            (book[0],),
        ).fetchall()
        assert [tuple(row) for row in pages] == [
            (1, "一頁目", "narrative", 1),
            (2, "二頁目", "narrative", 1),
        ]
        run = conn.execute("SELECT state, qa_state, qa_reviewer FROM ocr_runs WHERE id=?", (run_id,)).fetchone()
        assert tuple(run) == ("completed", "approved", "tester")


def test_stage_rejects_source_image_changed_after_ocr(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "本文"))

    Image.new("RGB", (100, 140), "black").save(input_pages[0].image_path)

    with pytest.raises(ValueError, match="source image changed"):
        stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0


def test_run_approval_rejects_unreviewed_required_pages(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "本文"))
    stage_run_for_qa(run_id, input_pages)

    with pytest.raises(ValueError, match="required QA pages remain"):
        approve_and_publish_run(run_id, "tester")


def test_page_approval_requires_classification(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "章題のような曖昧な文字列です"))
    stage_run_for_qa(run_id, input_pages)
    with with_db() as conn:
        conn.execute(
            "UPDATE ocr_page_results SET page_type='unknown', index_eligible=0 WHERE run_id=? AND page_no=1",
            (run_id,),
        )
        conn.commit()

    with pytest.raises(ValueError, match="classified"):
        review_qa_page(run_id, 1, "approved", None, "unknown", "normal_prose", "primary", None)


def test_classify_run_pages_is_conservative(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    save_page_result(run_id, _passed_page(1, input_pages[0].image_sha256, "目次\n第一章\n第二章"))
    long_text = "これは物語本文の文章です。" * 40
    save_page_result(run_id, _passed_page(2, input_pages[1].image_sha256, long_text))

    counts = classify_run_pages(run_id)
    assert counts["toc"] == 1
    assert counts["narrative"] == 1
    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no, layout_type FROM ocr_page_results WHERE run_id=? ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [tuple(row) for row in rows] == [(1, "structured"), (2, "normal_prose")]


def test_classify_run_pages_excludes_appended_sample(tmp_data_dir) -> None:
    upgrade_head()
    book_name = "sample-boundary"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    for page_no in range(1, 17):
        Image.new("RGB", (100, 140), "white").save(images_dir / f"{page_no:03d}.png")
    input_pages = collect_input_pages(book_name)
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)

    for page in input_pages:
        text = "これは物語本文として十分な長さを持つ文章です。" * 20
        if page.page_no == 12:
            text = "別作品 電子特別お試し版"
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, text))

    counts = classify_run_pages(run_id)

    assert counts["colophon_or_ad"] == 5
    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no, page_type, index_eligible, quality_flags_json "
            "FROM ocr_page_results WHERE run_id=? AND page_no>=11 ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [tuple(row[:3]) for row in rows] == [
        (11, "narrative", 1),
        (12, "colophon_or_ad", 0),
        (13, "colophon_or_ad", 0),
        (14, "colophon_or_ad", 0),
        (15, "colophon_or_ad", 0),
        (16, "colophon_or_ad", 0),
    ]
    assert "sample_content_boundary" in rows[1][3]
    assert all("sample_content_excluded" in row[3] for row in rows[2:])


def test_stage_requires_sample_boundary_but_not_every_excluded_page(tmp_data_dir) -> None:
    upgrade_head()
    book_name = "sample-boundary-qa"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    for page_no in range(1, 17):
        Image.new("RGB", (100, 140), "white").save(images_dir / f"{page_no:03d}.png")
    input_pages = collect_input_pages(book_name)
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        text = "これは物語本文として十分な長さを持つ文章です。" * 20
        if page.page_no == 12:
            text = "別作品 電子特別お試し版"
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, text))

    stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        required = conn.execute(
            "SELECT page_no FROM ocr_page_results WHERE run_id=? AND qa_state='required' ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [row[0] for row in required] == [1, 2, 3, 4, 5, 6, 7, 8, 12, 16]


@pytest.mark.parametrize(
    ("page_no", "page_count", "text", "expected"),
    [
        (79, 86, "本文中で目次という語に触れます。" * 160, "narrative"),
        (95, 98, "あとがき\n今回の執筆についてお話しします。" * 40, "narrative"),
        (97, 102, "物語の結末に続く文章です。" * 40, "narrative"),
        (95, 99, "発行所 発行者 電子書籍 無断転載 " * 30, "colophon_or_ad"),
    ],
)
def test_page_type_does_not_exclude_late_narrative(
    page_no: int,
    page_count: int,
    text: str,
    expected: str,
) -> None:
    assert (
        suggest_page_type(
            page_no=page_no,
            page_count=page_count,
            full_text=text,
            char_count=len(text),
        )
        == expected
    )


def test_qa_risk_detects_long_non_narrative_and_name_disagreement() -> None:
    assert detect_qa_risk_flags(
        page_type="colophon_or_ad",
        full_text="広告の説明です。" * 80,
        char_count=640,
        primary_text="広告の説明です。" * 80,
        external_text="",
    ) == {"page_type_text_conflict"}
    assert detect_qa_risk_flags(
        page_type="narrative",
        full_text="珀陽様がお見えになりました。",
        char_count=14,
        primary_text="珀陽様がお見えになりました。",
        external_text="伯陽様がお見えになりました。",
    ) == {"named_entity_candidate_disagreement"}


def test_qa_risk_ignores_unpaired_candidate_omissions() -> None:
    assert (
        detect_qa_risk_flags(
            page_type="narrative",
            full_text="茉莉花様とラーナシュが話しています。",
            char_count=18,
            primary_text="茉莉花様とラーナシュが話しています。",
            external_text="茉莉花様が話しています。",
        )
        == set()
    )


def test_qa_risk_detects_repetition_per_candidate_and_selected_text() -> None:
    repeated = "\n".join(["茉莉花は静かに書類へ目を落とした。"] * 3)
    assert detect_qa_risk_flags(
        page_type="narrative",
        full_text=repeated,
        char_count=len(repeated),
        primary_text=repeated,
        external_text="正常な外部OCR本文です。",
    ) == {"primary_text_repetition", "selected_text_repetition"}

    assert detect_qa_risk_flags(
        page_type="narrative",
        full_text="正常な採用本文です。",
        char_count=9,
        primary_text="正常な主OCR本文です。",
        external_text=repeated,
    ) == {"external_text_repetition"}


def test_classification_preserves_ocr_candidate_selection(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    result = _passed_page(1, input_pages[0].image_sha256, "目次\n第一章\n第二章")
    result["external_text"] = "外部OCR候補"
    result["selected_engine"] = "external"
    save_page_result(run_id, result)
    save_page_result(run_id, _passed_page(2, input_pages[1].image_sha256, "本文" * 200))

    classify_run_pages(run_id)

    with with_db() as conn:
        row = conn.execute(
            "SELECT primary_text, external_text, selected_engine FROM ocr_page_results WHERE run_id=? AND page_no=1",
            (run_id,),
        ).fetchone()
    assert tuple(row) == ("目次\n第一章\n第二章", "外部OCR候補", "external")


def test_stage_requires_risky_flags_but_not_routine_audit_flags(tmp_data_dir) -> None:
    upgrade_head()
    book_name = "qa-flag-selection"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    for page_no in range(1, 13):
        Image.new("RGB", (100, 140), "white").save(images_dir / f"{page_no:03d}.png")
    input_pages = collect_input_pages(book_name)
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)

    for page in input_pages:
        result = _passed_page(page.page_no, page.image_sha256, "これは通常の本文です。" * 40)
        if page.page_no == 9:
            result["quality_flags"] = [
                "cross_engine_consensus",
                "primary_text_repetition",
                "sample_content_excluded",
                "yomitoku_adjudication",
            ]
        if page.page_no == 10:
            result["quality_flags"] = ["external_ocr_more_complete"]
        save_page_result(run_id, result)

    stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no FROM ocr_page_results WHERE run_id=? AND qa_state='required' ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [row[0] for row in rows] == [1, 2, 3, 4, 5, 6, 7, 8, 10, 12]


def test_stage_requires_content_risks(tmp_data_dir) -> None:
    upgrade_head()
    book_name = "qa-name-risk"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    for page_no in range(1, 13):
        Image.new("RGB", (100, 140), "white").save(images_dir / f"{page_no:03d}.png")
    input_pages = collect_input_pages(book_name)
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)

    for page in input_pages:
        result = _passed_page(page.page_no, page.image_sha256, "これは通常の本文です。" * 40)
        if page.page_no == 9:
            result["primary_text"] = "本文です。" * 60 + "珀陽様が来ました。"
            result["external_text"] = "本文です。" * 60 + "伯陽様が来ました。"
            result["quality_flags"] = ["cross_engine_consensus", "yomitoku_adjudication"]
        if page.page_no == 10:
            result = _passed_page(
                page.page_no,
                page.image_sha256,
                "発行所 発行者 電子書籍 無断転載 " * 40,
            )
        save_page_result(run_id, result)

    stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no, qa_state, quality_flags_json FROM ocr_page_results "
            "WHERE run_id=? AND page_no IN (9, 10) ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [row[1] for row in rows] == ["required", "required"]
    assert "named_entity_candidate_disagreement" in rows[0][2]
    assert "page_type_text_conflict" in rows[1][2]


def test_failed_non_index_page_can_publish_as_image_only(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    save_page_result(run_id, _passed_page(1, input_pages[0].image_sha256, "本文"))
    failed = _passed_page(2, input_pages[1].image_sha256, "目次")
    failed["state"] = "failed"
    failed["error_message"] = "cross_engine_disagreement"
    failed["layout_type"] = "structured"
    save_page_result(run_id, failed)

    stage_run_for_qa(run_id, input_pages)
    review_qa_page(run_id, 1, "approved", None, "narrative", "normal_prose", "primary", None)
    review_qa_page(run_id, 2, "approved", None, "toc", "structured", "primary", None)
    approve_and_publish_run(run_id, "tester")

    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no, full_text, page_type, index_eligible FROM pages ORDER BY page_no"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        (1, "本文", "narrative", 1),
        (2, "", "toc", 0),
    ]


def test_failed_narrative_requires_reviewed_correction(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        failed = _passed_page(page.page_no, page.image_sha256, "誤読候補")
        failed["state"] = "failed"
        failed["error_message"] = "cross_engine_disagreement"
        save_page_result(run_id, failed)
    stage_run_for_qa(run_id, input_pages)

    with pytest.raises(ValueError, match="corrected text"):
        review_qa_page(run_id, 1, "approved", None, "narrative", "normal_prose", "primary", None)

    review_qa_page(
        run_id,
        1,
        "approved",
        "Codex画像照合済み",
        "narrative",
        "normal_prose",
        "codex",
        "正しい本文",
    )
