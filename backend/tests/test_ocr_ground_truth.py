from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from services.novel_db.connection import with_db
from services.novel_db.extractor import OcrPageResult
from services.novel_db.migrations import upgrade_head
from services.novel_db.ocr_ground_truth import (
    character_error_rate,
    list_ground_truth,
    seed_ground_truth,
    update_ground_truth,
)
from services.novel_db.ocr_run_store import collect_input_pages, prepare_run, save_page_result


def _passed_page(
    page_no: int, image_sha256: str, text: str, *, engine: str = "surya2", model: str = "model-sha"
) -> OcrPageResult:
    return {
        "runtime_manifest": {"schema_version": 1, "engine": engine, "model_revision": model},
        "page_no": page_no,
        "image_sha256": image_sha256,
        "state": "passed",
        "full_text": text,
        "char_count": len(text),
        "raw_output": text,
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


@pytest.fixture
def corpus_run(tmp_data_dir) -> tuple[int, Path]:
    upgrade_head()
    book_name = "ground-truth-test"
    images_dir = Path(tmp_data_dir["KINDLE_NOVEL_IMAGES_DIR"]) / book_name
    images_dir.mkdir(parents=True)
    image_path = images_dir / "001.png"
    Image.new("RGB", (100, 140), "white").save(image_path)
    pages = collect_input_pages(book_name)
    run_id, _ = prepare_run(book_name, "surya2", "model-sha", pages)
    save_page_result(run_id, _passed_page(1, pages[0].image_sha256, "吾輩は猫である"))
    return run_id, image_path


def test_character_error_rate_is_weightable() -> None:
    assert character_error_rate("abcdef", "abcxef") == (1, 6, pytest.approx(1 / 6))
    assert character_error_rate("吾輩は\n猫", "吾輩 は猫") == (0, 4, 0)


def test_seed_is_draft_and_idempotent(corpus_run) -> None:
    run_id, _ = corpus_run
    samples = [{"run_id": run_id, "page_no": 1}]
    assert seed_ground_truth(samples) == 1
    assert seed_ground_truth(samples) == 0
    result = list_ground_truth()
    assert result["total_count"] == 1
    assert result["verified_count"] == 0
    assert result["aggregate_cer"] is None
    assert result["entries"][0]["reference_text"] == ""
    unknown_metrics = next(metric for metric in result["metrics_by_page_type"] if metric["page_type"] == "unknown")
    assert unknown_metrics["total_count"] == 1
    assert unknown_metrics["verified_count"] == 0
    assert unknown_metrics["aggregate_cer"] is None


def test_verified_entry_calculates_cer(corpus_run) -> None:
    run_id, _ = corpus_run
    seed_ground_truth([{"run_id": run_id, "page_no": 1}])
    entry_id = list_ground_truth()["entries"][0]["id"]
    update_ground_truth(
        entry_id,
        reference_text="吾輩は犬である",
        page_type="narrative",
        layout_type="normal_prose",
        state="verified",
        note="猫を犬へ変更した評価例",
    )
    result = list_ground_truth()
    assert result["verified_count"] == 1
    assert result["total_edit_distance"] == 1
    assert result["total_reference_chars"] == 7
    assert result["aggregate_cer"] == pytest.approx(1 / 7)
    narrative_metrics = next(metric for metric in result["metrics_by_page_type"] if metric["page_type"] == "narrative")
    assert narrative_metrics == {
        "page_type": "narrative",
        "total_count": 1,
        "verified_count": 1,
        "total_edit_distance": 1,
        "total_reference_chars": 7,
        "aggregate_cer": pytest.approx(1 / 7),
    }
    layout_metrics = next(
        metric for metric in result["metrics_by_layout_type"] if metric["layout_type"] == "normal_prose"
    )
    assert layout_metrics["aggregate_cer"] == pytest.approx(1 / 7)


def test_verified_entry_reuses_cached_metric(corpus_run, monkeypatch) -> None:
    run_id, _ = corpus_run
    seed_ground_truth([{"run_id": run_id, "page_no": 1}])
    entry_id = list_ground_truth()["entries"][0]["id"]
    update_ground_truth(
        entry_id,
        reference_text="吾輩は犬である",
        page_type="narrative",
        layout_type="normal_prose",
        state="verified",
        note=None,
    )
    expected = list_ground_truth()

    def fail_recalculation(*_args):
        raise AssertionError("unchanged metric must be served from the page cache")

    monkeypatch.setattr(
        "services.novel_db.ocr_ground_truth.character_error_rate",
        fail_recalculation,
    )
    assert list_ground_truth() == expected


def test_changed_ocr_text_invalidates_only_affected_metric(corpus_run) -> None:
    run_id, _ = corpus_run
    seed_ground_truth([{"run_id": run_id, "page_no": 1}])
    entry_id = list_ground_truth()["entries"][0]["id"]
    update_ground_truth(
        entry_id,
        reference_text="吾輩は犬である",
        page_type="narrative",
        layout_type="normal_prose",
        state="verified",
        note=None,
    )
    before = list_ground_truth()
    assert before["total_edit_distance"] == 1

    with with_db() as conn:
        conn.execute(
            "UPDATE ocr_page_results SET full_text=? WHERE run_id=? AND page_no=1",
            ("吾輩は鳥である", run_id),
        )
        conn.commit()

    after = list_ground_truth()
    assert after["total_edit_distance"] == 1
    with with_db() as conn:
        cached = conn.execute(
            "SELECT cer_edit_distance, cer_reference_chars, "
            "cer_reference_sha256, cer_hypothesis_sha256 "
            "FROM ocr_ground_truth_pages WHERE id=?",
            (entry_id,),
        ).fetchone()
    assert tuple(cached[:2]) == (1, 7)
    assert all(len(str(value)) == 64 for value in cached[2:])


def test_draft_transition_clears_cached_metric(corpus_run) -> None:
    run_id, _ = corpus_run
    seed_ground_truth([{"run_id": run_id, "page_no": 1}])
    entry_id = list_ground_truth()["entries"][0]["id"]
    update_ground_truth(
        entry_id,
        reference_text="吾輩は犬である",
        page_type="narrative",
        layout_type="normal_prose",
        state="verified",
        note=None,
    )
    update_ground_truth(
        entry_id,
        reference_text="吾輩は犬である",
        page_type="narrative",
        layout_type="normal_prose",
        state="draft",
        note=None,
    )
    with with_db() as conn:
        cached = conn.execute(
            "SELECT cer_edit_distance, cer_reference_chars, "
            "cer_reference_sha256, cer_hypothesis_sha256 "
            "FROM ocr_ground_truth_pages WHERE id=?",
            (entry_id,),
        ).fetchone()
    assert tuple(cached) == (None, None, None, None)


def test_verification_rejects_unknown_type_and_changed_image(corpus_run) -> None:
    run_id, image_path = corpus_run
    seed_ground_truth([{"run_id": run_id, "page_no": 1}])
    entry_id = list_ground_truth()["entries"][0]["id"]
    with pytest.raises(ValueError, match="classified"):
        update_ground_truth(
            entry_id,
            reference_text="正解",
            page_type="unknown",
            layout_type="normal_prose",
            state="verified",
            note=None,
        )

    Image.new("RGB", (100, 140), "black").save(image_path)
    with pytest.raises(ValueError, match="source image changed"):
        update_ground_truth(
            entry_id,
            reference_text="正解",
            page_type="narrative",
            layout_type="normal_prose",
            state="verified",
            note=None,
        )
