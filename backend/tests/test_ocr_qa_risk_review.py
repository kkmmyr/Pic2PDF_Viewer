"""OCR QA risk, classification, and review tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from services.novel_db.connection import with_db
from services.novel_db.extractor import OcrPageResult
from services.novel_db.migrations import upgrade_head
from services.novel_db.ocr_page_classification import classify_run_pages
from services.novel_db.ocr_page_types import suggest_page_type
from services.novel_db.ocr_qa_publication import approve_and_publish_run
from services.novel_db.ocr_qa_review import review_qa_page
from services.novel_db.ocr_qa_risk import annotate_run_qa_risks, detect_qa_risk_flags
from services.novel_db.ocr_qa_staging import stage_run_for_qa
from services.novel_db.ocr_run_store import collect_input_pages, prepare_run, save_page_result


def _unique_content(length: int, *, start: int = 0) -> str:
    return "".join(chr(0x4E00 + start + index) for index in range(length))


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
    non_narrative = _unique_content(640)
    assert detect_qa_risk_flags(
        page_type="colophon_or_ad",
        full_text=non_narrative,
        char_count=640,
        primary_text=non_narrative,
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


def test_qa_risk_detects_unselected_longer_external_candidate() -> None:
    primary = _unique_content(300)
    external = primary + _unique_content(40, start=500)

    assert detect_qa_risk_flags(
        page_type="narrative",
        full_text=primary,
        char_count=len(primary),
        primary_text=primary,
        external_text=external,
    ) == {"unselected_external_candidate_more_complete"}

    assert (
        detect_qa_risk_flags(
            page_type="narrative",
            full_text=external,
            char_count=len(external),
            primary_text=primary,
            external_text=external,
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


@pytest.mark.parametrize(
    ("primary_text", "external_text", "full_text"),
    [
        ("ChatGPT 通知の処理が完了しました", "正常な補助候補です。", "正常な採用本文です。"),
        ("正常な主系候補です。", "Kindleカタログ UI改善 要件整理", "正常な採用本文です。"),
        ("正常な主系候補です。", "正常な補助候補です。", "KindleカタログのUI改善を完了しました"),
    ],
)
def test_qa_risk_detects_ui_overlay_text_in_any_candidate(
    primary_text: str,
    external_text: str,
    full_text: str,
) -> None:
    assert detect_qa_risk_flags(
        page_type="narrative",
        full_text=full_text,
        char_count=len(full_text),
        primary_text=primary_text,
        external_text=external_text,
    ) == {"ui_overlay_text_detected"}


def test_qa_risk_does_not_treat_generic_notification_words_as_ui_overlay() -> None:
    narrative = "城門から届いた通知を読み、使者は任務が完了しましたと告げた。"
    assert (
        detect_qa_risk_flags(
            page_type="narrative",
            full_text=narrative,
            char_count=len(narrative),
            primary_text=narrative,
            external_text=narrative,
        )
        == set()
    )


def test_qa_risk_uses_selected_engine_text(tmp_data_dir) -> None:
    upgrade_head()
    book_name = "qa-selected-engine"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    Image.new("RGB", (100, 140), "white").save(images_dir / "001.png")
    input_pages = collect_input_pages(book_name)
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    repeated = "\n".join(["茉莉花は静かに書類へ目を落とした。"] * 3)
    result = _passed_page(1, input_pages[0].image_sha256, repeated)
    result["external_text"] = _unique_content(300)
    save_page_result(run_id, result)
    with with_db() as conn:
        conn.execute(
            "UPDATE ocr_page_results SET selected_engine='external', page_type='narrative' "
            "WHERE run_id=? AND page_no=1",
            (run_id,),
        )
        conn.commit()

    assert annotate_run_qa_risks(run_id) == set()
    with with_db() as conn:
        flags = conn.execute(
            "SELECT quality_flags_json FROM ocr_page_results WHERE run_id=? AND page_no=1",
            (run_id,),
        ).fetchone()[0]
    assert "primary_text_repetition" in flags
    assert "selected_text_repetition" not in flags


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
        result = _passed_page(page.page_no, page.image_sha256, _unique_content(400))
        if page.page_no == 9:
            result["quality_flags"] = [
                "cross_engine_consensus",
                "primary_text_repetition",
                "sample_content_excluded",
                "yomitoku_adjudication",
            ]
        if page.page_no == 10:
            result["quality_flags"] = ["external_ocr_more_complete"]
        if page.page_no == 11:
            result["quality_flags"] = ["external_low_confidence_more_complete_candidate"]
        if page.page_no == 12:
            result["quality_flags"] = ["external_recovered_primary_repetition"]
        save_page_result(run_id, result)

    stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no FROM ocr_page_results WHERE run_id=? AND qa_state='required' ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [row[0] for row in rows] == [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12]


def test_review_assisted_engine_requires_every_page(tmp_data_dir) -> None:
    upgrade_head()
    book_name = "qa-review-assisted"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    for page_no in range(1, 13):
        Image.new("RGB", (100, 140), "white").save(images_dir / f"{page_no:03d}.png")
    input_pages = collect_input_pages(book_name)
    run_id, _ = prepare_run(
        book_name,
        "qwen35_dots_review_v1",
        "fixed-composite-model",
        input_pages,
    )

    for page in input_pages:
        save_page_result(
            run_id,
            _passed_page(page.page_no, page.image_sha256, _unique_content(400)),
        )

    stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no FROM ocr_page_results WHERE run_id=? AND qa_state='required' ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [row[0] for row in rows] == list(range(1, 13))


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
        if page.page_no == 11:
            result["external_text"] = "ChatGPT KindleカタログUI改善要件整理"
        save_page_result(run_id, result)

    stage_run_for_qa(run_id, input_pages)

    with with_db() as conn:
        rows = conn.execute(
            "SELECT page_no, qa_state, quality_flags_json FROM ocr_page_results "
            "WHERE run_id=? AND page_no IN (9, 10, 11) ORDER BY page_no",
            (run_id,),
        ).fetchall()
    assert [row[1] for row in rows] == ["required", "required", "required"]
    assert "named_entity_candidate_disagreement" in rows[0][2]
    assert "page_type_text_conflict" in rows[1][2]
    assert "ui_overlay_text_detected" in rows[2][2]


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


def test_review_rejects_unused_corrected_text(staged_book) -> None:
    book_name, input_pages = staged_book
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", input_pages)
    for page in input_pages:
        save_page_result(run_id, _passed_page(page.page_no, page.image_sha256, "機械候補"))
    stage_run_for_qa(run_id, input_pages)

    with pytest.raises(ValueError, match="corrected text requires selected engine codex"):
        review_qa_page(
            run_id,
            1,
            "approved",
            "画像照合済み",
            "narrative",
            "normal_prose",
            "primary",
            "補正文",
        )

    with with_db() as conn:
        row = conn.execute(
            "SELECT qa_state, selected_engine, corrected_text FROM ocr_page_results WHERE run_id=? AND page_no=1",
            (run_id,),
        ).fetchone()
    assert tuple(row) == ("required", "primary", None)
