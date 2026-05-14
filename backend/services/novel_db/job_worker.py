"""再構築ジョブの worker スレッド実装。

NovelDbJobQueue から生成され、rebuild_jobs テーブルの queued ジョブを
古い順に取り出して実行する。
"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path

from config import KINDLE_NOVEL_IMAGES_DIR
from utils.logger import get_logger

from .builder import _resolve_images_dir, _store_ocr_pages, rebuild_from_pages
from .connection import with_db
from .extractor import run_ocr_subprocess
from .full_builder import build_book_contexts, build_book_full

logger = get_logger(__name__)


class NovelDbJobWorker:
    """再構築ジョブの実行 + DB 更新を担う worker。

    NovelDbJobQueue が生成し、stop_event / wakeup の 2 つの Event を共有する。
    """

    def __init__(self, stop_event: threading.Event, wakeup: threading.Event) -> None:
        self._stop_event = stop_event
        self._wakeup = wakeup
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ----- worker ループ -----

    def run(self) -> None:
        """worker スレッドのエントリーポイント。NovelDbJobQueue が Thread に渡す。"""
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
            except Exception as e:
                logger.exception("Job %d failed", job["id"])
                self._mark_finished(job["id"], "failed", error=str(e) + "\n" + traceback.format_exc())
            finally:
                self._is_running = False

    # ----- DB 操作 -----

    def _claim_next_job(self) -> dict | None:
        """次のジョブを running に更新して取り出す。無ければ None。"""
        with with_db() as conn:
            row = conn.execute(
                "SELECT id, job_type, target_id, mode FROM rebuild_jobs "
                "WHERE state='queued' ORDER BY enqueued_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job_id, job_type, target_id, mode = row
            conn.execute(
                "UPDATE rebuild_jobs SET state='running', "
                "started_at=datetime('now') WHERE id = ?",
                (job_id,),
            )
            conn.commit()
        self._is_running = True
        return {"id": job_id, "job_type": job_type, "target_id": target_id, "mode": mode}

    def _mark_finished(self, job_id: int, state: str, *, error: str | None = None) -> None:
        with with_db() as conn:
            conn.execute(
                "UPDATE rebuild_jobs SET state = ?, finished_at = datetime('now'), "
                "error_message = ? WHERE id = ?",
                (state, error, job_id),
            )
            conn.commit()

    def _update_progress(self, job_id: int, done: int, total: int) -> None:
        with with_db() as conn:
            conn.execute(
                "UPDATE rebuild_jobs SET progress_done = ?, progress_total = ? WHERE id = ?",
                (done, total, job_id),
            )
            conn.commit()

    def _update_step(self, job_id: int, step: str) -> None:
        with with_db() as conn:
            conn.execute(
                "UPDATE rebuild_jobs SET current_step = ? WHERE id = ?",
                (step, job_id),
            )
            conn.commit()

    def _update_detail(self, job_id: int, detail: str) -> None:
        with with_db() as conn:
            conn.execute(
                "UPDATE rebuild_jobs SET current_detail = ? WHERE id = ?",
                (detail, job_id),
            )
            conn.commit()

    # ----- ジョブ実行 -----

    def _execute_job(self, job: dict) -> None:
        job_id = job["id"]
        job_type = job["job_type"]
        target_id = job["target_id"]
        mode = job["mode"]

        targets = self._resolve_targets(job_type, target_id)
        total = len(targets)
        self._update_progress(job_id, 0, total)

        if mode == "ocr":
            images_dirs = [_resolve_images_dir(name) for name in targets]
            for done, (book_name, pages) in enumerate(run_ocr_subprocess(images_dirs), start=1):
                if not pages:
                    raise ValueError(f"no PNG images found for: {book_name}")
                _store_ocr_pages(book_name, pages)
                self._update_progress(job_id, done, total)
                logger.info("Job %d OCR progress: %d/%d (%s)", job_id, done, total, book_name)
        elif mode == "full_build":
            def _step_cb(msg: str, _jid: int = job_id) -> None:
                self._update_step(_jid, msg)

            for done, book_name in enumerate(targets, start=1):
                _prefix = f"冊 {done}/{total} 処理中 | " if total > 1 else ""

                def _detail_cb(detail: str, _jid: int = job_id, _p: str = _prefix) -> None:
                    self._update_detail(_jid, _p + detail)

                build_book_full(book_name, step_callback=_step_cb, detail_callback=_detail_cb)
                self._update_progress(job_id, done, total)
                logger.info("Job %d full_build progress: %d/%d (%s)", job_id, done, total, book_name)
        elif mode == "generate_contexts":
            def _ctx_step_cb(msg: str, _jid: int = job_id) -> None:
                self._update_step(_jid, msg)

            for done, book_name in enumerate(targets, start=1):
                _prefix = f"冊 {done}/{total} 処理中 | " if total > 1 else ""

                def _ctx_detail_cb(detail: str, _jid: int = job_id, _p: str = _prefix) -> None:
                    self._update_detail(_jid, _p + detail)

                build_book_contexts(book_name, step_callback=_ctx_step_cb, detail_callback=_ctx_detail_cb)
                self._update_progress(job_id, done, total)
                logger.info("Job %d generate_contexts progress: %d/%d (%s)", job_id, done, total, book_name)
        else:
            # rebuild: pages.full_text → chunks/embeddings
            for done, book_name in enumerate(targets, start=1):
                with with_db() as conn:
                    rebuild_from_pages(conn, book_name)
                self._update_progress(job_id, done, total)
                logger.info("Job %d rebuild progress: %d/%d (%s)", job_id, done, total, book_name)

    def _resolve_targets(self, job_type: str, target_id: str | None) -> list[str]:
        """job_type に応じて再構築対象書籍名のリストを返す。"""
        if job_type == "book":
            if not target_id:
                raise ValueError("'book' job requires target_id")
            return [target_id]
        if job_type == "all":
            return _list_all_book_names()
        if job_type == "series":
            if not target_id:
                raise ValueError("'series' job requires target_id (series_id)")
            return _list_books_in_series(target_id)
        raise ValueError(f"Unknown job_type: {job_type}")


def _list_all_book_names() -> list[str]:
    """images/ 配下のサブディレクトリ名を書籍 stem として返す。"""
    images_dir = Path(KINDLE_NOVEL_IMAGES_DIR)
    if not images_dir.exists():
        return []
    return sorted(d.name for d in images_dir.iterdir() if d.is_dir())


def _list_books_in_series(series_id: str) -> list[str]:
    """meta.json から指定 series_id に属する novel 書籍の stem 一覧を返す。"""
    from services.meta_store import load_meta
    images_dir = Path(KINDLE_NOVEL_IMAGES_DIR)
    meta = load_meta("novel")
    names: list[str] = []
    for key, entry in meta.items():
        if entry.get("series_id") != series_id:
            continue
        if not key.endswith(".pdf"):
            continue
        stem = key[: -len(".pdf")]
        if (images_dir / stem).is_dir():
            names.append(stem)
    return sorted(names)
