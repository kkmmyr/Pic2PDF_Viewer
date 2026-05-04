"""ソースキー単位の threading.Lock を貸し出す共通ロックマネージャ。

`meta_store` / `genre_store` のように「ソース文字列ごとに直列化したい」ストア層
で同じロック辞書管理パターンを再実装していたものを集約する。マネージャごとに
内部辞書を持つため、ストア間でロックは独立する。
"""
import threading


class SourceLockManager:
    """ソース文字列をキーに `threading.Lock` を遅延生成・キャッシュする。"""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._mutex = threading.Lock()

    def get(self, source: str) -> threading.Lock:
        with self._mutex:
            lock = self._locks.get(source)
            if lock is None:
                lock = threading.Lock()
                self._locks[source] = lock
            return lock
