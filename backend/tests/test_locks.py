"""
utils.locks.SourceLockManager のユニットテスト。

ストア層共通の遅延生成ロックマネージャの並行性を検証する。

実行方法:
    cd backend
    uv run pytest tests/test_locks.py -v
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.locks import SourceLockManager


class TestSourceLockManager:
    def test_same_source_returns_same_lock(self):
        mgr = SourceLockManager()
        a = mgr.get("doujin")
        b = mgr.get("doujin")
        assert a is b

    def test_different_sources_return_different_locks(self):
        mgr = SourceLockManager()
        a = mgr.get("doujin")
        b = mgr.get("comic")
        assert a is not b

    def test_lock_is_threading_lock(self):
        """返り値は threading.Lock 互換（acquire / release を持つ）。"""
        mgr = SourceLockManager()
        lock = mgr.get("doujin")
        assert hasattr(lock, "acquire")
        assert hasattr(lock, "release")
        # 取得・解放が動く
        assert lock.acquire(blocking=False) is True
        lock.release()

    def test_concurrent_get_no_duplicate_creation(self):
        """100 スレッドで同じ source を取得してもインスタンスは 1 つ。"""
        mgr = SourceLockManager()
        results: list = []
        result_lock = threading.Lock()

        def _worker():
            lock = mgr.get("doujin")
            with result_lock:
                results.append(lock)

        threads = [threading.Thread(target=_worker) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        first = results[0]
        for r in results[1:]:
            assert r is first

    def test_independent_managers_are_isolated(self):
        """異なる SourceLockManager インスタンスはロックを共有しない。"""
        a = SourceLockManager()
        b = SourceLockManager()
        lock_a = a.get("doujin")
        lock_b = b.get("doujin")
        assert lock_a is not lock_b

    def test_lock_provides_mutual_exclusion(self):
        """同じ source の lock は相互排他になる（カウンタが lost update せず最終値が一致）。"""
        mgr = SourceLockManager()
        counter = {"value": 0}

        def _increment():
            with mgr.get("doujin"):
                # lock 内で 1000 回足す
                for _ in range(1000):
                    counter["value"] += 1

        threads = [threading.Thread(target=_increment) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counter["value"] == 10 * 1000
