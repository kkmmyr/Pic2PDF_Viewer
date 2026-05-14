"""再構築ジョブの全体ロック + キュー API。

worker スレッドが 1 つ走り、rebuild_jobs テーブルから queued ジョブを古い順に
取り出して実行する。実行ロジックは job_worker.NovelDbJobWorker に委譲。
検索 / 質問 API は `is_running` フラグを見て 503 を返す。
詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §8。
"""
from __future__ import annotations

import threading
from typing import Literal

from utils.logger import get_logger

from .connection import with_db
from .job_worker import NovelDbJobWorker
from .schema import init_schema

logger = get_logger(__name__)

JobType = Literal["book", "series", "all"]
JobMode = Literal["rebuild", "ocr", "full_build", "generate_contexts"]
JobState = Literal["queued", "running", "completed", "failed", "canceled"]


class NovelDbJobQueue:
    """再構築ジョブのキュー管理。実行ロジックは NovelDbJobWorker に委譲。

    - `enqueue()`: ジョブを INSERT して worker を起こす
    - `cancel()`: queued なジョブのみ canceled に更新
    - `is_running`: worker が現在ジョブ実行中かどうか
    - `start() / stop()`: アプリ lifespan で呼ぶ
    """

    def __init__(self) -> None:
        self._wakeup = threading.Event()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._worker = NovelDbJobWorker(self._stop_event, self._wakeup)

    @property
    def is_running(self) -> bool:
        return self._worker.is_running

    # ----- ライフサイクル -----

    def start(self) -> None:
        """schema 初期化 + 旧 JobMode migration + worker スレッド起動。"""
        with with_db() as conn:
            init_schema(conn)
            conn.execute(
                "UPDATE rebuild_jobs SET state='failed', "
                "error_message='aborted by server restart' "
                "WHERE state='running'"
            )
            # 旧 JobMode 名を正規化（Phase 59）
            conn.execute("UPDATE rebuild_jobs SET mode='rebuild' WHERE mode='pdf_text'")
            conn.execute("UPDATE rebuild_jobs SET mode='ocr' WHERE mode='reocr'")
            conn.commit()

        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker.run, name="NovelDbJobQueue", daemon=True
        )
        self._worker_thread.start()
        logger.info("NovelDbJobQueue started")

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        self._wakeup.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=timeout)
            self._worker_thread = None
        logger.info("NovelDbJobQueue stopped")

    # ----- 公開 API -----

    def enqueue(
        self,
        job_type: JobType,
        target_id: str | None = None,
        mode: JobMode = "rebuild",
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
                "progress_total, progress_done, current_step, current_detail "
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


def _row_to_running(row: tuple) -> dict:
    job_id, job_type, target_id, mode, started_at, total, done, current_step, current_detail = row
    return {
        "id": job_id,
        "type": job_type,
        "target_id": target_id,
        "mode": mode,
        "started_at": started_at,
        "progress_total": total,
        "progress_done": done,
        "current_step": current_step,
        "current_detail": current_detail,
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
