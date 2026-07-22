"""再構築ジョブの worker スレッド実装。

NovelDbJobQueue から生成され、rebuild_jobs テーブルの queued ジョブを
古い順に取り出して実行する。
"""

from __future__ import annotations

import threading
import traceback
from pathlib import Path

import config
from utils.logger import get_logger

from .builder import rebuild_from_pages
from .connection import with_db
from .extractor import iter_ocr_pages
from .full_builder import build_book_contexts, build_book_full
from .ocr_staging import collect_input_pages, mark_run_failed, prepare_run, publish_run, save_page_result
from .relation_extractor import generate_book_relations
from .series_meta import book_names_for_series, load_book_series_ids

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 書籍一覧クエリ（job_worker 専用ヘルパー）
# ---------------------------------------------------------------------------


def _list_all_book_names() -> list[str]:
    images_dir = Path(config.KINDLE_NOVEL_IMAGES_DIR)
    if not images_dir.exists():
        return []
    return sorted(d.name for d in images_dir.iterdir() if d.is_dir())


def _list_books_needing_ocr() -> list[str]:
    images_dir = Path(config.KINDLE_NOVEL_IMAGES_DIR)
    if not images_dir.exists():
        return []
    all_dirs = {d.name for d in images_dir.iterdir() if d.is_dir()}
    if not all_dirs:
        return []
    with with_db() as conn:
        rows = conn.execute("SELECT name FROM books WHERE ocr_done_at IS NOT NULL").fetchall()
    done = {r[0] for r in rows}
    return sorted(all_dirs - done)


def _list_books_with_ocr_done() -> list[str]:
    with with_db() as conn:
        rows = conn.execute("SELECT name FROM books WHERE ocr_done_at IS NOT NULL ORDER BY name").fetchall()
    return [r[0] for r in rows]


def _list_books_needing_full_build() -> list[str]:
    with with_db() as conn:
        rows = conn.execute(
            "SELECT name FROM books WHERE ocr_done_at IS NOT NULL AND indexed_at IS NULL ORDER BY name"
        ).fetchall()
    return [r[0] for r in rows]


def _list_books_needing_contexts() -> list[str]:
    with with_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT b.name FROM books b "
            "JOIN pages p ON p.book_id = b.id "
            "JOIN chunks c ON c.page_id = p.id "
            "WHERE b.ocr_done_at IS NOT NULL AND c.contextual_text IS NULL "
            "ORDER BY b.name"
        ).fetchall()
    return [r[0] for r in rows]


def _list_books_in_series(series_id: str) -> list[str]:
    images_dir = Path(config.KINDLE_NOVEL_IMAGES_DIR)
    return sorted(book_name for book_name in book_names_for_series(series_id) if (images_dir / book_name).is_dir())


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
                "UPDATE rebuild_jobs SET state='running', started_at=datetime('now', '+9 hours') WHERE id = ?",
                (job_id,),
            )
            conn.commit()
        self._is_running = True
        return {"id": job_id, "job_type": job_type, "target_id": target_id, "mode": mode}

    def _mark_finished(self, job_id: int, state: str, *, error: str | None = None) -> None:
        with with_db() as conn:
            conn.execute(
                "UPDATE rebuild_jobs SET state = ?, finished_at = datetime('now', '+9 hours'), "
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

        targets = self._resolve_targets(job_type, target_id, mode)
        total = len(targets)
        self._update_progress(job_id, 0, total)

        if mode == "ocr":
            engine = config.app_settings.OCR_ENGINE.casefold()
            model = config.app_settings.SURYA_MODEL_REVISION if engine == "surya2" else engine
            contexts: dict[str, tuple[int, list]] = {}
            tasks = []
            for book_name in targets:
                input_pages = collect_input_pages(book_name)
                run_id, pending_tasks = prepare_run(book_name, engine, model, input_pages)
                contexts[book_name] = (run_id, input_pages)
                tasks.extend(pending_tasks)

            try:
                for book_name, page in iter_ocr_pages(tasks):
                    context = contexts.get(book_name)
                    if context is None:
                        raise RuntimeError(f"OCR worker returned unknown book: {book_name}")
                    run_id, _ = context
                    save_page_result(run_id, page)
                    self._update_detail(job_id, f"{book_name} | page {page['page_no']}")
            except Exception as exc:
                for run_id, _ in contexts.values():
                    mark_run_failed(run_id, str(exc))
                raise

            failures: list[str] = []
            for done, book_name in enumerate(targets, start=1):
                run_id, input_pages = contexts[book_name]
                try:
                    publish_run(run_id, input_pages)
                except Exception as exc:
                    mark_run_failed(run_id, str(exc))
                    failures.append(f"{book_name}: {exc}")
                self._update_progress(job_id, done, total)
                logger.info("Job %d OCR progress: %d/%d (%s)", job_id, done, total, book_name)
            if failures:
                raise RuntimeError("OCR quality gate failed: " + "; ".join(failures))
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
        elif mode == "generate_relations":

            def _rel_detail_cb(detail: str, _jid: int = job_id) -> None:
                self._update_detail(_jid, detail)

            series_ids = load_book_series_ids()
            for done, book_name in enumerate(targets, start=1):
                series_id = series_ids.get(book_name)
                if not series_id:
                    logger.warning("Job %d: no series_id for %s, skipping", job_id, book_name)
                    self._update_progress(job_id, done, total)
                    continue
                with with_db() as conn:
                    generate_book_relations(conn, book_name, series_id, detail_callback=_rel_detail_cb)
                self._update_progress(job_id, done, total)
                logger.info("Job %d generate_relations progress: %d/%d (%s)", job_id, done, total, book_name)
        else:
            # rebuild: pages.full_text → chunks/embeddings
            for done, book_name in enumerate(targets, start=1):
                with with_db() as conn:
                    rebuild_from_pages(conn, book_name)
                self._update_progress(job_id, done, total)
                logger.info("Job %d rebuild progress: %d/%d (%s)", job_id, done, total, book_name)

    def _resolve_targets(self, job_type: str, target_id: str | None, mode: str) -> list[str]:
        """job_type と mode に応じて再構築対象書籍名のリストを返す。

        job_type="all" の場合:
          - mode="ocr"               → OCR 未完了の書籍のみ（images_dir 存在 & ocr_done_at 未設定）
          - mode="full_build"        → Full Build 未完了の書籍のみ（ocr_done_at 設定済み & indexed_at 未設定）
          - mode="generate_contexts" → コンテキスト未生成チャンクが存在する書籍のみ
          - それ以外（rebuild）      → OCR 完了済みの書籍のみ（ocr_done_at 設定済み）
        """
        if job_type == "book":
            if not target_id:
                raise ValueError("'book' job requires target_id")
            return [target_id]
        if job_type == "all":
            if mode == "ocr":
                return _list_books_needing_ocr()
            if mode == "full_build":
                return _list_books_needing_full_build()
            if mode == "generate_contexts":
                return _list_books_needing_contexts()
            if mode == "generate_relations":
                return _list_books_with_ocr_done()
            return _list_books_with_ocr_done()
        if job_type == "series":
            if not target_id:
                raise ValueError("'series' job requires target_id (series_id)")
            return _list_books_in_series(target_id)
        raise ValueError(f"Unknown job_type: {job_type}")
