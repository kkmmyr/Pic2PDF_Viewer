"""Application service for executing one OCR background job."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Protocol

import config
from utils.logger import get_logger

from .extractor import OcrPageResult, OcrProgressEvent, OcrTask
from .ocr_run_store import OcrInputPage

logger = get_logger(__name__)


class OcrPageIterator(Protocol):
    def __call__(
        self,
        tasks: list[OcrTask],
        *,
        progress_callback: Callable[[OcrProgressEvent], None] | None = None,
    ) -> Iterator[tuple[str, OcrPageResult]]: ...


@dataclass(frozen=True)
class OcrJobDependencies:
    collect_input_pages: Callable[[str], list[OcrInputPage]]
    prepare_run: Callable[[str, str, str, list[OcrInputPage]], tuple[int, list[OcrTask]]]
    iter_ocr_pages: OcrPageIterator
    save_page_result: Callable[[int, OcrPageResult], None]
    mark_run_failed: Callable[[int, str], None]
    stage_run_for_qa: Callable[[int, list[OcrInputPage]], None]


@dataclass(frozen=True)
class OcrJobCallbacks:
    update_detail: Callable[[int, str], None]
    update_progress: Callable[[int, int, int], None]


@dataclass(frozen=True)
class OcrRunContext:
    run_id: int
    input_pages: list[OcrInputPage]


def format_ocr_progress(progress: OcrProgressEvent) -> str:
    """Map a worker progress event to the established job detail string."""
    book_name = progress.get("book_name")
    page_no = progress.get("page_no")
    total_pages = progress.get("total_pages")
    generation = progress.get("server_generation")
    attempt = progress.get("attempt_count")
    detail = progress.get("detail")
    parts = [str(progress.get("stage", "ocr"))]
    if book_name:
        parts.append(str(book_name))
    if page_no is not None:
        parts.append(f"page {page_no}/{total_pages or '?'}")
    if attempt is not None:
        parts.append(f"attempt {attempt}")
    if generation is not None:
        parts.append(f"server {generation}")
    if detail:
        parts.append(str(detail))
    return " | ".join(parts)


def execute_ocr_job(
    job_id: int,
    targets: list[str],
    total: int,
    callbacks: OcrJobCallbacks,
    deps: OcrJobDependencies,
) -> None:
    """Prepare runs, consume the worker process, and stage each run for QA."""
    engine = config.app_settings.OCR_ENGINE.casefold()
    model = config.app_settings.SURYA_MODEL_REVISION if engine == "surya2" else engine
    contexts, tasks = _prepare_runs(targets, engine, model, deps)
    try:
        _consume_worker_pages(job_id, tasks, contexts, callbacks, deps)
    except Exception as exc:
        for context in contexts.values():
            deps.mark_run_failed(context.run_id, str(exc))
        raise
    _stage_runs_for_qa(job_id, targets, total, contexts, callbacks, deps)


def _prepare_runs(
    targets: list[str],
    engine: str,
    model: str,
    deps: OcrJobDependencies,
) -> tuple[dict[str, OcrRunContext], list[OcrTask]]:
    contexts: dict[str, OcrRunContext] = {}
    tasks: list[OcrTask] = []
    for book_name in targets:
        input_pages = deps.collect_input_pages(book_name)
        run_id, pending_tasks = deps.prepare_run(book_name, engine, model, input_pages)
        contexts[book_name] = OcrRunContext(run_id, input_pages)
        tasks.extend(pending_tasks)
    return contexts, tasks


def _consume_worker_pages(
    job_id: int,
    tasks: list[OcrTask],
    contexts: dict[str, OcrRunContext],
    callbacks: OcrJobCallbacks,
    deps: OcrJobDependencies,
) -> None:
    def _report_progress(progress: OcrProgressEvent) -> None:
        callbacks.update_detail(job_id, format_ocr_progress(progress))

    for book_name, page in deps.iter_ocr_pages(tasks, progress_callback=_report_progress):
        context = contexts.get(book_name)
        if context is None:
            raise RuntimeError(f"OCR worker returned unknown book: {book_name}")
        deps.save_page_result(context.run_id, page)
        callbacks.update_detail(job_id, f"{book_name} | page {page['page_no']}")


def _stage_runs_for_qa(
    job_id: int,
    targets: list[str],
    total: int,
    contexts: dict[str, OcrRunContext],
    callbacks: OcrJobCallbacks,
    deps: OcrJobDependencies,
) -> None:
    failures: list[str] = []
    for done, book_name in enumerate(targets, start=1):
        context = contexts[book_name]
        try:
            deps.stage_run_for_qa(context.run_id, context.input_pages)
        except Exception as exc:
            deps.mark_run_failed(context.run_id, str(exc))
            failures.append(f"{book_name}: {exc}")
        callbacks.update_progress(job_id, done, total)
        logger.info("Job %d OCR progress: %d/%d (%s)", job_id, done, total, book_name)
    if failures:
        raise RuntimeError("OCR quality gate failed: " + "; ".join(failures))
