"""同人誌入力フォルダの自動監視サービス。

`config.DOUJIN_INPUT_DIR` を一定間隔でスキャンし、トップレベルの ZIP / フォルダ構成が
前回スキャンと同一（= コピーが安定した）と判定できたタイミングで自動的に PDF 生成
ジョブを起動する。生成ロックは `services.generate_service.generate_lock` を手動
`POST /api/generate` と共有し、二重実行を防ぐ。

状態遷移（`tick()` 1 回ごと）:
    - 入力ディレクトリ不在              → "input_missing"（スナップショットは保持）
    - スナップショットが空              → "idle"（last_attempted もクリア）
    - 前回スキャンと異なる              → "waiting_stable"（コピー進行中とみなす）
    - 前回と同一 かつ 直前の自動起動と同一 → "idle"（失敗残骸、自動再試行しない）
    - 前回と同一 かつ ロック取得済み     → "running"
    - 前回と同一 かつ ロック空き        → ジョブ起動 → "running"
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime

import config
from services.generate_service import generate_lock, start_generate_job
from services.job_manager import GenerateJob
from utils.file_utils import is_zip_file
from utils.logger import get_logger

logger = get_logger(__name__)

# (name, kind, ...kind 別の追加フィールド) のタプル集合でスナップショットを表現する。
# zip:    (name, "zip", size, mtime)
# folder: (name, "folder", 再帰ファイル数, 合計サイズ, 最大 mtime)
_Snapshot = frozenset[tuple]


@dataclass
class PendingItem:
    name: str
    kind: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class DoujinWatcher:
    """DOUJIN_INPUT_DIR を定期監視し、安定検知後に自動生成ジョブを起動する。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self.state: str = "disabled"
        self.last_scan_at: str | None = None
        self.pending_items: list[PendingItem] = []
        self.last_auto_job: dict[str, str] | None = None
        self.retry_blocked: bool = False
        self._snapshot: _Snapshot | None = None
        self._last_attempted: _Snapshot | None = None

    def clear_last_attempted(self) -> None:
        """手動実行成功時に呼ぶ。手動実行 = 再試行の意思表示として自動再試行を許可する。"""
        self._last_attempted = None

    # ----- ライフサイクル -----

    async def start(self) -> None:
        if not config.DOUJIN_WATCH_ENABLED or not config.DOUJIN_INPUT_DIR:
            self.state = "disabled"
            return
        if self._task and not self._task.done():
            return
        self.state = "idle"
        self._task = asyncio.create_task(self._loop(), name="DoujinWatcher")
        logger.info("DoujinWatcher started (interval=%ds)", config.DOUJIN_WATCH_INTERVAL_SEC)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("DoujinWatcher stopped")

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("DoujinWatcher tick failed")
            await asyncio.sleep(config.DOUJIN_WATCH_INTERVAL_SEC)

    # ----- スキャン・判定ロジック -----

    async def tick(self) -> None:
        """1 回分のスキャン・判定を行う。sleep を含まないため単体テストで直接呼べる。"""
        self.last_scan_at = _now_iso()
        input_dir = config.DOUJIN_INPUT_DIR

        if not input_dir or not os.path.isdir(input_dir):
            self.state = "input_missing"
            self.retry_blocked = False
            return

        try:
            snapshot = self._scan(input_dir)
        except OSError:
            logger.exception("DoujinWatcher: failed to scan %s", input_dir)
            self.state = "input_missing"
            self.retry_blocked = False
            return

        self.pending_items = [PendingItem(name=t[0], kind=t[1]) for t in sorted(snapshot)]

        if not snapshot:
            self.state = "idle"
            self.retry_blocked = False
            self._snapshot = snapshot
            self._last_attempted = None
            return

        if snapshot != self._snapshot:
            self.state = "waiting_stable"
            self.retry_blocked = False
            self._snapshot = snapshot
            return

        # スナップショットが安定（前回スキャンと同一）
        if snapshot == self._last_attempted:
            self.state = "idle"
            self.retry_blocked = True
            return

        if generate_lock.locked():
            self.state = "running"
            self.retry_blocked = False
            return

        self._last_attempted = snapshot
        self.retry_blocked = False
        job = await start_generate_job(trigger="auto", on_done=self._record_auto_job_done)
        # start_generate_job が None を返すのはロック競合時のみ（asyncio 単一スレッドでは
        # 事実上発生しないが、防御的に running 扱いにする）。
        self.state = "running"
        if job is None:
            logger.warning("DoujinWatcher: start_generate_job unexpectedly returned None")

    def _record_auto_job_done(self, job: GenerateJob) -> None:
        self.last_auto_job = {
            "job_id": job.job_id,
            "status": job.status.value if hasattr(job.status, "value") else str(job.status),
            "finished_at": _now_iso(),
        }

    def _scan(self, input_dir: str) -> _Snapshot:
        entries: list[tuple] = []
        with os.scandir(input_dir) as it:
            for entry in it:
                try:
                    if entry.is_file():
                        if is_zip_file(entry.name):
                            stat = entry.stat()
                            entries.append((entry.name, "zip", stat.st_size, stat.st_mtime))
                    elif entry.is_dir():
                        file_count, total_size, max_mtime = self._scan_folder(entry.path)
                        entries.append((entry.name, "folder", file_count, total_size, max_mtime))
                except OSError:
                    logger.warning("DoujinWatcher: skip unreadable entry %s", entry.path)
        return frozenset(entries)

    def _scan_folder(self, folder_path: str) -> tuple[int, int, float]:
        file_count = 0
        total_size = 0
        max_mtime = 0.0
        for root, _dirs, files in os.walk(folder_path):
            for name in files:
                path = os.path.join(root, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                file_count += 1
                total_size += stat.st_size
                max_mtime = max(max_mtime, stat.st_mtime)
        return file_count, total_size, max_mtime


# main.py の lifespan から start/stop する単一インスタンス
doujin_watcher = DoujinWatcher()
