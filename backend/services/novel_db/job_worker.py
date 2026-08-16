"""Queue loop and compatibility facade for novel database background jobs."""

from __future__ import annotations

import threading
import traceback

from utils.logger import get_logger

from . import job_targets as _job_targets
from .builder import rebuild_from_pages
from .extractor import iter_ocr_pages
from .full_builder import build_book_contexts, build_book_full
from .job_executor import JobExecutionDependencies, execute_job
from .job_state import claim_next_job, mark_finished, update_detail, update_progress, update_step
from .job_targets import resolve_targets
from .ocr_job_application import OcrJobDependencies
from .ocr_qa_staging import stage_run_for_qa
from .ocr_run_store import collect_input_pages, mark_run_failed, prepare_run, save_page_result
from .relation_extractor import generate_book_relations
from .series_meta import load_book_series_ids

logger = get_logger(__name__)

# Compatibility for private helpers imported by older extensions.
_list_all_book_names = _job_targets.list_all_book_names
_list_books_needing_ocr = _job_targets.list_books_needing_ocr
_list_books_with_ocr_done = _job_targets.list_books_with_ocr_done
_list_books_needing_full_build = _job_targets.list_books_needing_full_build
_list_books_needing_contexts = _job_targets.list_books_needing_contexts
_list_books_in_series = _job_targets.list_books_in_series


class NovelDbJobWorker:
    """Claim queued jobs and delegate persistence, targeting, and execution."""

    def __init__(self, stop_event: threading.Event, wakeup: threading.Event) -> None:
        self._stop_event = stop_event
        self._wakeup = wakeup
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def run(self) -> None:
        while not self._stop_event.is_set():
            self._wakeup.wait(timeout=5.0)
            self._wakeup.clear()
            self._drain_queue()

    def _drain_queue(self) -> None:
        while not self._stop_event.is_set():
            job = self._claim_next_job()
            if job is None:
                return
            try:
                self._execute_job(job)
                self._mark_finished(job["id"], "completed")
            except Exception as exc:
                logger.exception("Job %d failed", job["id"])
                self._mark_finished(job["id"], "failed", error=str(exc) + "\n" + traceback.format_exc())
            finally:
                self._is_running = False

    def _claim_next_job(self) -> dict | None:
        job = claim_next_job()
        if job is not None:
            self._is_running = True
        return job

    def _mark_finished(self, job_id: int, state: str, *, error: str | None = None) -> None:
        mark_finished(job_id, state, error=error)

    def _update_progress(self, job_id: int, done: int, total: int) -> None:
        update_progress(job_id, done, total)

    def _update_step(self, job_id: int, step: str) -> None:
        update_step(job_id, step)

    def _update_detail(self, job_id: int, detail: str) -> None:
        update_detail(job_id, detail)

    def _execute_job(self, job: dict) -> None:
        # Dependencies are assembled here to preserve established monkeypatch
        # points on this facade for tests and operational extensions.
        dependencies = JobExecutionDependencies(
            ocr=OcrJobDependencies(
                collect_input_pages=collect_input_pages,
                prepare_run=prepare_run,
                iter_ocr_pages=iter_ocr_pages,
                save_page_result=save_page_result,
                mark_run_failed=mark_run_failed,
                stage_run_for_qa=stage_run_for_qa,
            ),
            build_book_full=build_book_full,
            build_book_contexts=build_book_contexts,
            load_book_series_ids=load_book_series_ids,
            generate_book_relations=generate_book_relations,
            rebuild_from_pages=rebuild_from_pages,
        )
        execute_job(self, job, dependencies)

    def _resolve_targets(self, job_type: str, target_id: str | None, mode: str) -> list[str]:
        return resolve_targets(job_type, target_id, mode)
