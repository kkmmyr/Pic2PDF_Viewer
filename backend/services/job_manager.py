import threading
import uuid
from enum import Enum
from typing import Optional
from config import JOB_MAX_JOBS


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerateJob:
    """1回のPDF生成ジョブを表すデータクラス。"""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status: JobStatus = JobStatus.PENDING
        self.current_item: Optional[str] = None
        self.files: list[str] = []
        self.message: str = ""
        self.error: Optional[str] = None
        self._lock = threading.Lock()

    def to_dict(self) -> dict[str, object]:
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status.value,
                "current_item": self.current_item,
                "files": list(self.files),
                "message": self.message,
                "error": self.error,
            }

    def update(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)


class JobStore:
    """実行中・完了済みジョブを保持するスレッドセーフなストア。"""

    _MAX_JOBS = JOB_MAX_JOBS

    def __init__(self):
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

    def get(self, job_id: str) -> Optional[GenerateJob]:
        with self._lock:
            return self._jobs.get(job_id)


class GenerateState:
    """PDF生成の進捗状態を管理するスレッドセーフなシングルトンクラス。
    (後方互換: /api/status エンドポイントで使用)
    """

    _instance = None
    _class_lock = threading.Lock()

    def __new__(cls):
        with cls._class_lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._lock = threading.Lock()
                instance._current_item: Optional[str] = None
                cls._instance = instance
        return cls._instance

    def set_current_item(self, item: Optional[str]) -> None:
        with self._lock:
            self._current_item = item

    def get_current_item(self) -> Optional[str]:
        with self._lock:
            return self._current_item
