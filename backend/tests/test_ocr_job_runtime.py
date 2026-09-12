"""OCR設定の参照時点とrunへ渡す版情報を公開worker入口で固定する。"""

import threading
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

import config
from services.novel_db import job_worker
from services.novel_db.qwen_dots_worker import COMPOSITE_MODEL_REVISION


@pytest.fixture
def worker_calls(monkeypatch):
    worker = job_worker.NovelDbJobWorker(threading.Event(), threading.Event())
    calls = Mock()
    for name in ("_resolve_targets", "_update_progress", "_update_detail"):
        monkeypatch.setattr(worker, name, getattr(calls, name))
    for name in (
        "collect_input_pages",
        "prepare_run",
        "iter_ocr_pages",
        "save_page_result",
        "mark_run_failed",
        "stage_run_for_qa",
    ):
        monkeypatch.setattr(job_worker, name, getattr(calls, name))
    calls._resolve_targets.return_value = ["book"]
    calls.collect_input_pages.return_value = []
    calls.prepare_run.return_value = (11, [])
    calls.iter_ocr_pages.side_effect = lambda *args, **kwargs: iter([])
    return worker, calls


def _job(mode="ocr"):
    return {"id": 7, "job_type": "book", "target_id": "book", "mode": mode}


@pytest.mark.parametrize(
    ("configured", "engine", "model"),
    [
        ("Surya2", "surya2", "fixed-surya-revision"),
        ("QWEN35_DOTS_REVIEW_V1", "qwen35_dots_review_v1", COMPOSITE_MODEL_REVISION),
        ("YOMITOKU", "yomitoku", "yomitoku"),
        ("Unlisted", "unlisted", "unlisted"),
        (" surya2 ", " surya2 ", " surya2 "),
    ],
)
def test_model_selection_preserves_casefold_and_fallback(worker_calls, monkeypatch, configured, engine, model):
    worker, calls = worker_calls
    monkeypatch.setattr(
        config, "app_settings", SimpleNamespace(OCR_ENGINE=configured, SURYA_MODEL_REVISION="fixed-surya-revision")
    )

    worker._execute_job(_job())

    calls.prepare_run.assert_called_once_with("book", engine, model, [])


def test_settings_are_resolved_after_initial_progress_on_each_job(worker_calls, monkeypatch):
    worker, calls = worker_calls
    settings = iter(
        [
            SimpleNamespace(OCR_ENGINE="surya2", SURYA_MODEL_REVISION="revision-a"),
            SimpleNamespace(OCR_ENGINE="surya2", SURYA_MODEL_REVISION="revision-b"),
        ]
    )

    def progress(job_id, done, total):
        if done == 0:
            monkeypatch.setattr(config, "app_settings", next(settings))

    calls._update_progress.side_effect = progress
    worker._execute_job(_job())
    worker._execute_job(_job())

    assert calls.prepare_run.call_args_list == [
        call("book", "surya2", "revision-a", []),
        call("book", "surya2", "revision-b", []),
    ]


class UnavailableOcrSettings:
    @property
    def OCR_ENGINE(self):
        raise RuntimeError("OCR settings unavailable")


@pytest.mark.parametrize("targets", [[], ["book"]])
def test_settings_failure_precedes_run_preparation_even_without_targets(worker_calls, monkeypatch, targets):
    worker, calls = worker_calls
    calls._resolve_targets.return_value = targets
    monkeypatch.setattr(config, "app_settings", UnavailableOcrSettings())

    with pytest.raises(RuntimeError, match="OCR settings unavailable"):
        worker._execute_job(_job())

    assert calls.mock_calls == [call._resolve_targets("book", "book", "ocr"), call._update_progress(7, 0, len(targets))]


def test_target_failure_does_not_read_ocr_settings(worker_calls, monkeypatch):
    worker, calls = worker_calls
    calls._resolve_targets.side_effect = ValueError("target unavailable")
    monkeypatch.setattr(config, "app_settings", UnavailableOcrSettings())

    with pytest.raises(ValueError, match="target unavailable"):
        worker._execute_job(_job())
    calls._update_progress.assert_not_called()


@pytest.mark.parametrize("mode", ["rebuild", "full_build", "generate_contexts", "generate_relations"])
def test_non_ocr_job_does_not_read_ocr_settings(worker_calls, monkeypatch, mode):
    worker, calls = worker_calls
    calls._resolve_targets.return_value = []
    monkeypatch.setattr(config, "NOVEL_DB_LLM_BACKEND", "llama_server")
    monkeypatch.setattr(config, "app_settings", UnavailableOcrSettings())
    monkeypatch.setattr(job_worker, "load_book_series_ids", Mock(return_value={}))

    worker._execute_job(_job(mode))

    calls.collect_input_pages.assert_not_called()


@pytest.mark.parametrize("failure_point", ["collect_input_pages", "prepare_run"])
def test_partial_preparation_failure_keeps_existing_failure_scope(worker_calls, failure_point):
    worker, calls = worker_calls
    calls._resolve_targets.return_value = ["book", "broken"]
    first_result = [] if failure_point == "collect_input_pages" else (11, [])
    getattr(calls, failure_point).side_effect = [first_result, ValueError("prepare failed")]

    with pytest.raises(ValueError, match="prepare failed"):
        worker._execute_job(_job())

    calls.mark_run_failed.assert_not_called()
    calls.iter_ocr_pages.assert_not_called()
    calls.stage_run_for_qa.assert_not_called()
