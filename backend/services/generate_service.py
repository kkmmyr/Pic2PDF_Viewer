"""PDF 生成ジョブの実行ロジック（手動 API と自動フォルダ監視の共有コード経路）。

`generate_lock` で手動 `POST /api/generate` と `DoujinWatcher` の自動起動を直列化する。
どちらも `start_generate_job()` を経由することで、ロック取得・ジョブ生成・
バックグラウンド実行・ロック解放が同一のコードパスを通る。
"""

import asyncio
from collections.abc import Callable
from typing import Literal

import config
from services.job_manager import GenerateJob, JobStatus, JobStore
from services.meta_store import update_meta_locked
from services.pdf_generator import scan_and_generate
from utils.logger import get_logger

logger = get_logger(__name__)

TriggerType = Literal["manual", "auto"]

job_store = JobStore()
generate_lock = asyncio.Lock()

_active_job_id: str | None = None
_background_tasks: set[asyncio.Task[None]] = set()


def get_active_job_id() -> str | None:
    """現在ロックを保持して実行中のジョブ ID（実行中がなければ None）。"""
    return _active_job_id


def _run_generate_job(job: GenerateJob) -> None:
    """同期ワーカー: executor スレッドで PDF 生成ジョブを実行する。"""

    def progress_callback(item_name: str):
        job.update(current_item=item_name)
        logger.info("Processing: %s", item_name)

    try:
        job.update(status=JobStatus.RUNNING, current_item="Starting...")

        result = scan_and_generate(
            config.DOUJIN_INPUT_DIR,
            None,  # image-only モード: PDF 生成をスキップ
            config.THUMBNAIL_DIR,
            config.IMAGES_DIR,
            config.COMPLETE_DIR,
            progress_callback=progress_callback,
        )

        # 新規生成ファイルにのみ genre: "オリジナル" を初期書き込み（再生成時は保持）
        if result.generated:

            def _init_genre(data):
                for name in result.generated:
                    if name not in data:
                        data[name] = {"genre": "オリジナル"}

            update_meta_locked("doujin", _init_genre)

        failed_dicts = [{"name": n, "error": e} for n, e in result.failed_items]
        if failed_dicts:
            message = f"Generation complete: {len(result.generated)} succeeded, {len(failed_dicts)} failed"
        else:
            message = "Generation complete"

        job.update(
            status=JobStatus.COMPLETED,
            current_item=None,
            files=result.generated,
            failed_items=failed_dicts,
            message=message,
        )
        logger.info("Job %s completed: %d files, %d failed", job.job_id, len(result.generated), len(failed_dicts))

    except Exception as e:
        logger.exception("Job %s failed", job.job_id)
        job.update(status=JobStatus.FAILED, current_item=None, error=str(e))


async def _run_generate_job_async(job: GenerateJob) -> None:
    await asyncio.to_thread(_run_generate_job, job)


async def start_generate_job(
    trigger: TriggerType = "manual",
    on_done: Callable[[GenerateJob], None] | None = None,
) -> GenerateJob | None:
    """生成ロックが空いていればジョブを作成しバックグラウンド実行を開始する。

    ロック取得済みの場合は None を返す（呼び出し側が 409 等でハンドリングする）。
    `generate_lock.locked()` チェックから `acquire()` までの間に await を挟まないため、
    asyncio のシングルスレッド実行下で競合は発生しない。
    """
    global _active_job_id

    if generate_lock.locked():
        return None
    await generate_lock.acquire()

    job = job_store.create(trigger=trigger)
    _active_job_id = job.job_id

    async def _wrapped() -> None:
        global _active_job_id
        try:
            await _run_generate_job_async(job)
        finally:
            _active_job_id = None
            generate_lock.release()
            if on_done is not None:
                on_done(job)

    task = asyncio.create_task(_wrapped(), name=f"generate-{job.job_id}")
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return job
