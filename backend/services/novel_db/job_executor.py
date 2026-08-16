"""Mode-specific execution for novel database background jobs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from utils.logger import get_logger

from .connection import with_db
from .ocr_job_application import OcrJobCallbacks, OcrJobDependencies, execute_ocr_job

logger = get_logger(__name__)


@dataclass(frozen=True)
class JobExecutionDependencies:
    ocr: OcrJobDependencies
    build_book_full: Callable[..., Any]
    build_book_contexts: Callable[..., Any]
    load_book_series_ids: Callable[..., Any]
    generate_book_relations: Callable[..., Any]
    rebuild_from_pages: Callable[..., Any]


def execute_job(worker: Any, job: dict, deps: JobExecutionDependencies) -> None:
    """Execute one claimed job using the worker's observable progress hooks."""
    job_id = job["id"]
    mode = job["mode"]
    targets = worker._resolve_targets(job["job_type"], job["target_id"], mode)
    total = len(targets)
    worker._update_progress(job_id, 0, total)

    if mode == "ocr":
        execute_ocr_job(
            job_id,
            targets,
            total,
            OcrJobCallbacks(
                update_detail=worker._update_detail,
                update_progress=worker._update_progress,
            ),
            deps.ocr,
        )
    elif mode == "full_build":
        _execute_full_build(worker, job_id, targets, total, deps)
    elif mode == "generate_contexts":
        _execute_contexts(worker, job_id, targets, total, deps)
    elif mode == "generate_relations":
        _execute_relations(worker, job_id, targets, total, deps)
    else:
        _execute_rebuild(worker, job_id, targets, total, deps)


def _execute_full_build(
    worker: Any,
    job_id: int,
    targets: list[str],
    total: int,
    deps: JobExecutionDependencies,
) -> None:
    def _step_cb(msg: str, _jid: int = job_id) -> None:
        worker._update_step(_jid, msg)

    for done, book_name in enumerate(targets, start=1):
        prefix = f"冊 {done}/{total} 処理中 | " if total > 1 else ""

        def _detail_cb(detail: str, _jid: int = job_id, _prefix: str = prefix) -> None:
            worker._update_detail(_jid, _prefix + detail)

        deps.build_book_full(book_name, step_callback=_step_cb, detail_callback=_detail_cb)
        worker._update_progress(job_id, done, total)
        logger.info("Job %d full_build progress: %d/%d (%s)", job_id, done, total, book_name)


def _execute_contexts(
    worker: Any,
    job_id: int,
    targets: list[str],
    total: int,
    deps: JobExecutionDependencies,
) -> None:
    def _step_cb(msg: str, _jid: int = job_id) -> None:
        worker._update_step(_jid, msg)

    for done, book_name in enumerate(targets, start=1):
        prefix = f"冊 {done}/{total} 処理中 | " if total > 1 else ""

        def _detail_cb(detail: str, _jid: int = job_id, _prefix: str = prefix) -> None:
            worker._update_detail(_jid, _prefix + detail)

        deps.build_book_contexts(book_name, step_callback=_step_cb, detail_callback=_detail_cb)
        worker._update_progress(job_id, done, total)
        logger.info("Job %d generate_contexts progress: %d/%d (%s)", job_id, done, total, book_name)


def _execute_relations(
    worker: Any,
    job_id: int,
    targets: list[str],
    total: int,
    deps: JobExecutionDependencies,
) -> None:
    def _detail_cb(detail: str, _jid: int = job_id) -> None:
        worker._update_detail(_jid, detail)

    series_ids = deps.load_book_series_ids()
    for done, book_name in enumerate(targets, start=1):
        series_id = series_ids.get(book_name)
        if not series_id:
            logger.warning("Job %d: no series_id for %s, skipping", job_id, book_name)
            worker._update_progress(job_id, done, total)
            continue
        with with_db() as conn:
            deps.generate_book_relations(conn, book_name, series_id, detail_callback=_detail_cb)
        worker._update_progress(job_id, done, total)
        logger.info("Job %d generate_relations progress: %d/%d (%s)", job_id, done, total, book_name)


def _execute_rebuild(
    worker: Any,
    job_id: int,
    targets: list[str],
    total: int,
    deps: JobExecutionDependencies,
) -> None:
    for done, book_name in enumerate(targets, start=1):
        with with_db() as conn:
            deps.rebuild_from_pages(conn, book_name)
        worker._update_progress(job_id, done, total)
        logger.info("Job %d rebuild progress: %d/%d (%s)", job_id, done, total, book_name)
