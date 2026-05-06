"""ソース別ジョブ状態をスレッドセーフに管理する汎用マネージャー。"""
import threading
from collections.abc import Callable


class JobStateManager[T]:
    """ソース文字列をキーにジョブ状態を保持し、get/reset をスレッドセーフに提供する。

    Args:
        idle_factory: idle 状態のデフォルトインスタンスを返す callable。
        running_factory: status="running" のインスタンスを返す callable（reset 用）。
    """

    def __init__(
        self,
        idle_factory: Callable[[], T],
        running_factory: Callable[[], T],
    ) -> None:
        self._states: dict[str, T] = {}
        self._lock = threading.Lock()
        self._idle_factory = idle_factory
        self._running_factory = running_factory

    def get(self, source: str) -> T:
        """ソースのジョブ状態を返す。未登録の場合は idle 状態で初期化してから返す。"""
        with self._lock:
            if source not in self._states:
                self._states[source] = self._idle_factory()
            return self._states[source]

    def reset(self, source: str) -> None:
        """ソースのジョブ状態を running でリセットする（ジョブ開始直前に呼ぶ）。"""
        with self._lock:
            self._states[source] = self._running_factory()
