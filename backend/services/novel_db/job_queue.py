"""再構築ジョブの全体ロック + キュー。

worker スレッドが 1 つ走り、rebuild_jobs テーブルから queued ジョブを古い順に
取り出して実行する。検索 / 質問 API は `is_running` フラグを見て 503 を返す。
詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §8。
"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Literal

from config import KINDLE_NOVEL_IMAGES_DIR
from utils.logger import get_logger

from .builder import ocr_book, rebuild_from_pages
from .connection import with_db
from .full_builder import build_book_full
from .schema import init_schema

logger = get_logger(__name__)

JobType = Literal["book", "series", "all"]
# "rebuild": チャンク化・embedding 再構築（OCR 済みの pages.full_text を使う）
# "ocr"    : OCR ステップ（images/*.png → pages.full_text）
# "pdf_text"/"reocr": 旧モード名。DB に残った既存ジョブとの互換性のため "rebuild" と同じ動作にする
JobMode = Literal["rebuild", "ocr", "pdf_text", "reocr", "full_build"]
JobState = Literal["queued", "running", "completed", "failed", "canceled"]


class NovelDbJobQueue:
    """再構築ジョブのキュー + 単一 worker 実装。

    - `enqueue()`: ジョブを INSERT して worker を起こす
    - `cancel()`: queued なジョブのみ canceled に更新
    - `is_running`: worker が現在ジョブ実行中かどうか
    - `start() / stop()`: アプリ lifespan で呼ぶ
    """

    def __init__(self) -> None:
        self._wakeup = threading.Event()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._is_running = False  # True のとき検索 / 質問 API は 503

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ----- ライフサイクル -----

    def start(self) -> None:
        """schema 初期化 + worker スレッドを起動する。"""
        with with_db() as conn:
            init_schema(conn)
            # 前回未完で残った running ジョブは failed に倒しておく（再起動安全性）
            conn.execute(
                "UPDATE rebuild_jobs SET state='failed', "
                "error_message='aborted by server restart' "
                "WHERE state='running'"
            )
            conn.commit()

        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run, name="NovelDbJobQueue", daemon=True
        )
        self._worker.start()
        logger.info("NovelDbJobQueue started")

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        self._wakeup.set()
        if self._worker:
            self._worker.join(timeout=timeout)
            self._worker = None
        logger.info("NovelDbJobQueue stopped")

    # ----- 公開 API -----

    def enqueue(
        self,
        job_type: JobType,
        target_id: str | None = None,
        mode: JobMode = "pdf_text",
    ) -> tuple[int, int]:
        """ジョブを INSERT して worker を起こす。

        Returns:
            (job_id, queued_position): キュー内の順番（1 = 次に実行）
        """
        with with_db() as conn:
            cur = conn.execute(
                "INSERT INTO rebuild_jobs (job_type, target_id, mode) VALUES (?, ?, ?)",
                (job_type, target_id, mode),
            )
            job_id = cur.lastrowid
            queued_position = conn.execute(
                "SELECT COUNT(*) FROM rebuild_jobs WHERE state='queued' AND id <= ?",
                (job_id,),
            ).fetchone()[0]
            conn.commit()
        self._wakeup.set()
        logger.info(
            "Job enqueued: id=%d type=%s target=%s mode=%s position=%d",
            job_id, job_type, target_id, mode, queued_position,
        )
        return job_id, queued_position

    def cancel(self, job_id: int) -> Literal["canceled", "running", "not_found"]:
        with with_db() as conn:
            row = conn.execute(
                "SELECT state FROM rebuild_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return "not_found"
            if row[0] != "queued":
                return "running" if row[0] == "running" else "not_found"
            conn.execute(
                "UPDATE rebuild_jobs SET state='canceled', "
                "finished_at=datetime('now') WHERE id = ? AND state='queued'",
                (job_id,),
            )
            conn.commit()
        logger.info("Job canceled: id=%d", job_id)
        return "canceled"

    def get_status(self) -> dict:
        with with_db() as conn:
            current = conn.execute(
                "SELECT id, job_type, target_id, mode, started_at, "
                "progress_total, progress_done "
                "FROM rebuild_jobs WHERE state='running' "
                "ORDER BY started_at LIMIT 1"
            ).fetchone()
            queued = conn.execute(
                "SELECT id, job_type, target_id, mode, enqueued_at "
                "FROM rebuild_jobs WHERE state='queued' "
                "ORDER BY enqueued_at"
            ).fetchall()
            recent = conn.execute(
                "SELECT id, job_type, target_id, mode, state, finished_at, error_message "
                "FROM rebuild_jobs "
                "WHERE state IN ('completed', 'failed', 'canceled') "
                "ORDER BY finished_at DESC LIMIT 5"
            ).fetchall()

        return {
            "is_running": current is not None,
            "current_job": _row_to_running(current) if current else None,
            "queued_jobs": [_row_to_queued(r) for r in queued],
            "recent_finished": [_row_to_finished(r) for r in recent],
        }

    # ----- worker 実装 -----

    def _run(self) -> None:
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
        return {
            "id": job_id,
            "job_type": job_type,
            "target_id": target_id,
            "mode": mode,
        }

    def _mark_finished(self, job_id: int, state: JobState, *, error: str | None = None) -> None:
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

    def _execute_job(self, job: dict) -> None:
        job_id = job["id"]
        job_type = job["job_type"]
        target_id = job["target_id"]
        mode = job["mode"]

        targets = self._resolve_targets(job_type, target_id)
        total = len(targets)
        self._update_progress(job_id, 0, total)

        if mode in ("ocr", "reocr"):
            # OCR ステップ: images → pages.full_text
            # 複数書籍を連続処理するためエンジンを 1 度だけ初期化する
            from .extractor import load_ocr_engine
            engine = load_ocr_engine()
            for done, book_name in enumerate(targets, start=1):
                ocr_book(book_name, engine=engine)
                self._update_progress(job_id, done, total)
                logger.info("Job %d OCR progress: %d/%d (%s)", job_id, done, total, book_name)
        elif mode == "full_build":
            # 全構築統合: rebuild_from_pages → summarize → extract_chars → char_summary → contexts
            for done, book_name in enumerate(targets, start=1):
                build_book_full(book_name)
                self._update_progress(job_id, done, total)
                logger.info("Job %d full_build progress: %d/%d (%s)", job_id, done, total, book_name)
        else:
            # rebuild / pdf_text（後方互換）: pages.full_text → chunks/embeddings
            for done, book_name in enumerate(targets, start=1):
                with with_db() as conn:
                    rebuild_from_pages(conn, book_name)
                self._update_progress(job_id, done, total)
                logger.info("Job %d rebuild progress: %d/%d (%s)", job_id, done, total, book_name)

    def _resolve_targets(self, job_type: JobType, target_id: str | None) -> list[str]:
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
        # 実在チェック（images ディレクトリが存在する書籍のみ）
        if (images_dir / stem).is_dir():
            names.append(stem)
    return sorted(names)


def _row_to_running(row: tuple) -> dict:
    job_id, job_type, target_id, mode, started_at, total, done = row
    return {
        "id": job_id,
        "type": job_type,
        "target_id": target_id,
        "mode": mode,
        "started_at": started_at,
        "progress_total": total,
        "progress_done": done,
    }


def _row_to_queued(row: tuple) -> dict:
    job_id, job_type, target_id, mode, enqueued_at = row
    return {
        "id": job_id,
        "type": job_type,
        "target_id": target_id,
        "mode": mode,
        "enqueued_at": enqueued_at,
    }


def _row_to_finished(row: tuple) -> dict:
    job_id, job_type, target_id, mode, state, finished_at, error_message = row
    return {
        "id": job_id,
        "type": job_type,
        "target_id": target_id,
        "mode": mode,
        "state": state,
        "finished_at": finished_at,
        "error_message": error_message,
    }


# 単一インスタンスを公開（main.py の lifespan から start/stop する）
job_queue = NovelDbJobQueue()
