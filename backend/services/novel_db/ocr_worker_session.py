"""Surya server session orchestration for the standalone OCR worker."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

try:
    from .ocr_provenance import collect_runtime_manifest
    from .ocr_worker_engines import (
        YomitokuAdjudicator,
        process_surya_task,
        read_image,
    )
    from .ocr_worker_protocol import OcrWorkerTask, emit, emit_progress, failed_payload, page_payload
    from .surya_runtime import SuryaClient
    from .surya_server import SuryaServer
    from .surya_types import OcrSessionPolicy
except ImportError:
    from ocr_provenance import collect_runtime_manifest
    from ocr_worker_engines import YomitokuAdjudicator, process_surya_task, read_image
    from ocr_worker_protocol import OcrWorkerTask, emit, emit_progress, failed_payload, page_payload
    from surya_runtime import SuryaClient
    from surya_server import SuryaServer
    from surya_types import OcrSessionPolicy


@dataclass(frozen=True)
class SuryaWorkerSettings:
    base_url: str
    server_kwargs: dict[str, str | None]
    client_kwargs: dict[str, Any]
    max_attempts: int
    policy_kwargs: dict[str, Any]
    crosscheck_all_pages: bool
    cross_engine_min_similarity: float
    external_quality_kwargs: dict[str, float]

    @classmethod
    def from_env(cls) -> SuryaWorkerSettings:
        return cls(
            base_url=os.environ.get("SURYA_INFERENCE_URL", "http://127.0.0.1:8768/v1"),
            server_kwargs={
                "executable": os.environ.get("SURYA_LLAMA_SERVER_PATH"),
                "model_path": os.environ.get("SURYA_MODEL_PATH"),
                "mmproj_path": os.environ.get("SURYA_MMPROJ_PATH"),
            },
            client_kwargs={
                "model": os.environ.get("SURYA_MODEL", "surya-ocr-2"),
                "timeout_sec": float(os.environ.get("SURYA_REQUEST_TIMEOUT_SEC", "600")),
                "min_ink_coverage": float(os.environ.get("OCR_QUALITY_MIN_INK_COVERAGE", "0.85")),
            },
            max_attempts=int(os.environ.get("SURYA_MAX_ATTEMPTS", "3")),
            policy_kwargs={
                "max_pages": int(os.environ.get("OCR_SERVER_MAX_PAGES", "24")),
                "consecutive_failure_limit": int(os.environ.get("OCR_SERVER_CONSECUTIVE_FAILURES", "2")),
                "failure_window": int(os.environ.get("OCR_SERVER_FAILURE_WINDOW", "8")),
                "failure_rate": float(os.environ.get("OCR_SERVER_FAILURE_RATE", "0.5")),
            },
            crosscheck_all_pages=os.environ.get("OCR_CROSSCHECK_ALL_PAGES", "true").lower() in {"1", "true", "yes"},
            cross_engine_min_similarity=float(os.environ.get("OCR_CROSS_ENGINE_MIN_SIMILARITY", "0.85")),
            external_quality_kwargs={
                "min_median_confidence": float(os.environ.get("OCR_EXTERNAL_CONFIDENCE_MEDIAN", "0.85")),
                "min_weighted_mean_confidence": float(os.environ.get("OCR_EXTERNAL_CONFIDENCE_WEIGHTED_MEAN", "0.75")),
                "max_low_confidence_char_ratio": float(
                    os.environ.get("OCR_EXTERNAL_LOW_CONFIDENCE_CHAR_RATIO", "0.25")
                ),
            },
        )


def run_surya(
    tasks: list[OcrWorkerTask],
    *,
    server_factory: Callable[..., Any] = SuryaServer,
    client_factory: Callable[..., Any] = SuryaClient,
    read_image_fn: Callable[[Path], tuple[bytes, str, Image.Image]] = read_image,
) -> None:
    settings = SuryaWorkerSettings.from_env()
    manifest_started = time.perf_counter()
    runtime_manifest = collect_runtime_manifest(
        "surya2",
        os.environ.get("OCR_MODEL_REVISION", "unversioned"),
    )
    manifest_collection_ms = round((time.perf_counter() - manifest_started) * 1000)
    adjudicator = YomitokuAdjudicator(settings.external_quality_kwargs)
    task_index = 0
    server_generation = 0
    total_pages = len(tasks)
    while task_index < total_pages:
        server_generation += 1
        policy = OcrSessionPolicy(**settings.policy_kwargs)
        restart_reason = "completed"
        init_started = time.perf_counter()
        with server_factory(settings.base_url, **settings.server_kwargs) as server:
            worker_init_ms = round((time.perf_counter() - init_started) * 1000)
            server_owned = server.owns_process
            emit_progress(
                "server_started",
                server_generation=server_generation,
                total_pages=total_pages,
                detail="worker_owned" if server_owned else "external",
            )
            client = client_factory(settings.base_url, **settings.client_kwargs)
            while task_index < total_pages:
                task = tasks[task_index]
                task_index += 1
                book_name = str(task["book_name"])
                page_no = int(task["page_no"])
                image_sha256 = ""
                result = None
                surya_failed = True
                page_started = time.perf_counter()
                emit_progress(
                    "page_started",
                    server_generation=server_generation,
                    total_pages=total_pages,
                    book_name=book_name,
                    page_no=page_no,
                )
                try:
                    read_started = time.perf_counter()
                    _, image_sha256, image = read_image_fn(Path(task["image_path"]))
                    image_read_ms = round((time.perf_counter() - read_started) * 1000)
                    execution = process_surya_task(
                        task,
                        image_sha256,
                        image,
                        client,
                        adjudicator,
                        max_attempts=settings.max_attempts,
                        crosscheck_all_pages=settings.crosscheck_all_pages,
                        cross_engine_min_similarity=settings.cross_engine_min_similarity,
                    )
                    image_sha256 = execution.image_sha256
                    result = execution.result
                    surya_failed = execution.surya_failed
                    processing_timing = {
                        "image_read_ms": image_read_ms,
                        **execution.processing_timing,
                        "total_ms": round((time.perf_counter() - page_started) * 1000),
                    }
                    emit(
                        page_payload(
                            execution.book_name,
                            execution.page_no,
                            execution.image_sha256,
                            execution.result,
                            server_generation,
                            layout_type=execution.layout_type,
                            primary_text=execution.primary_text,
                            external_text=execution.external_text,
                            primary_raw_output=execution.primary_raw_output,
                            external_raw_output=execution.external_raw_output,
                            candidate_manifest=execution.candidate_manifest,
                            processing_timing=processing_timing,
                            runtime_manifest=runtime_manifest,
                            run_timing={
                                "manifest_collection_ms": manifest_collection_ms,
                                "worker_init_ms": worker_init_ms,
                            },
                            selected_engine=execution.selected_engine,
                        )
                    )
                except Exception as exc:
                    emit(
                        failed_payload(
                            book_name,
                            page_no,
                            image_sha256,
                            exc,
                            server_generation,
                            processing_timing={"total_ms": round((time.perf_counter() - page_started) * 1000)},
                            runtime_manifest=runtime_manifest,
                            run_timing={
                                "manifest_collection_ms": manifest_collection_ms,
                                "worker_init_ms": worker_init_ms,
                            },
                        )
                    )

                emit_progress(
                    "page_completed",
                    server_generation=server_generation,
                    total_pages=total_pages,
                    book_name=book_name,
                    page_no=page_no,
                    attempt_count=result.attempt_count if result is not None else None,
                    detail=result.state if result is not None else "worker_error",
                )
                reason = policy.record(surya_failed)
                if reason is not None and task_index < total_pages and server_owned:
                    restart_reason = reason
                    break
                if reason is not None and task_index < total_pages and not server_owned:
                    emit_progress(
                        "server_restart_skipped",
                        server_generation=server_generation,
                        total_pages=total_pages,
                        detail=f"{reason}:external_server",
                    )
                    policy = OcrSessionPolicy(**settings.policy_kwargs)
            emit_progress(
                "server_stopping",
                server_generation=server_generation,
                total_pages=total_pages,
                detail=restart_reason,
            )
