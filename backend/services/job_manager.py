import threading
import uuid
from enum import StrEnum
from typing import Any

from config import JOB_MAX_JOBS


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerateJob:
    """1回のPDF生成ジョブを表すデータクラス。"""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.status: JobStatus = JobStatus.PENDING
        self.current_item: str | None = None
        self.files: list[str] = []
        # サイレント失敗を防ぐため、書籍単位の失敗を {name, error} で保持しレスポンスに含める
        self.failed_items: list[dict[str, str]] = []
        self.message: str = ""
        self.error: str | None = None
        self._lock = threading.Lock()

    def to_dict(self) -> dict[str, object]:
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status.value,
                "current_item": self.current_item,
                "files": list(self.files),
                "failed_items": list(self.failed_items),
                "message": self.message,
                "error": self.error,
            }

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)


class JobStore:
    """実行中・完了済みジョブを保持するスレッドセーフなストア。"""

    _MAX_JOBS = JOB_MAX_JOBS

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, GenerateJob] = {}
        self._order: list[str] = []

    def create(self) -> GenerateJob:
        job = GenerateJob(str(uuid.uuid4()))
        with self._lock:
            self._jobs[job.job_id] = job
            self._order.append(job.job_id)
            while len(self._order) > self._MAX_JOBS:
                old_id = self._order.pop(0)
                self._jobs.pop(old_id, None)
        return job

    def get(self, job_id: str) -> GenerateJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_active_current_item(self) -> str | None:
        """最新の RUNNING ジョブの current_item を返す。

        `/api/status` で「現在処理中のアイテム名」を取得するために使う。
        RUNNING のジョブがなければ None。
        """
        with self._lock:
            # 新しい順に走査して RUNNING ジョブを探す
            for job_id in reversed(self._order):
                job = self._jobs.get(job_id)
                if job is not None and job.status == JobStatus.RUNNING:
                    return job.current_item
        return None
