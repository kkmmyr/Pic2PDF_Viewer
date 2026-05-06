"""
services.job_state.JobStateManager のユニットテスト。

汎用ジェネリクス（auto_fill_service / series_resolver で使用）の挙動を確認する。

実行方法:
    cd backend
    uv run pytest tests/test_job_state.py -v
"""
import os
import sys
import threading
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.job_state import JobStateManager


@dataclass
class _FakeState:
    status: str = "idle"
    total: int = 0
    done: int = 0
    note: str = ""


def _idle() -> _FakeState:
    return _FakeState(status="idle")


def _running() -> _FakeState:
    return _FakeState(status="running")


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

class TestGet:
    def test_first_get_returns_idle(self):
        mgr = JobStateManager(_idle, _running)
        s = mgr.get("generated")
        assert s.status == "idle"

    def test_same_source_returns_same_instance(self):
        mgr = JobStateManager(_idle, _running)
        a = mgr.get("generated")
        b = mgr.get("generated")
        assert a is b

    def test_different_sources_return_different_instances(self):
        mgr = JobStateManager(_idle, _running)
        a = mgr.get("generated")
        b = mgr.get("kindle")
        assert a is not b
        assert a.status == "idle"
        assert b.status == "idle"

    def test_state_mutation_persists(self):
        """同じインスタンスが返るので状態の変更が次回 get でも見える。"""
        mgr = JobStateManager(_idle, _running)
        s = mgr.get("generated")
        s.note = "modified"

        s2 = mgr.get("generated")
        assert s2.note == "modified"


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_replaces_with_running_factory(self):
        mgr = JobStateManager(_idle, _running)
        mgr.get("generated")  # idle で初期化
        mgr.reset("generated")

        s = mgr.get("generated")
        assert s.status == "running"

    def test_reset_creates_fresh_instance(self):
        """reset 前後で異なるインスタンスになる。"""
        mgr = JobStateManager(_idle, _running)
        a = mgr.get("generated")
        a.note = "old"

        mgr.reset("generated")
        b = mgr.get("generated")

        assert a is not b
        assert b.note == ""  # 新規 _running() インスタンスなので空

    def test_reset_unrelated_source_does_not_affect_others(self):
        mgr = JobStateManager(_idle, _running)
        a = mgr.get("generated")
        a.note = "preserved"

        mgr.reset("kindle")

        assert mgr.get("generated").note == "preserved"
        assert mgr.get("kindle").status == "running"


# ---------------------------------------------------------------------------
# 並行性
# ---------------------------------------------------------------------------

class TestConcurrency:
    def test_concurrent_get_returns_same_instance(self):
        """10 スレッドで同じ source を get しても同一インスタンスが返る。"""
        mgr = JobStateManager(_idle, _running)
        results: list[_FakeState] = []
        lock = threading.Lock()

        def _worker():
            s = mgr.get("generated")
            with lock:
                results.append(s)

        threads = [threading.Thread(target=_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        first = results[0]
        for r in results[1:]:
            assert r is first

    def test_concurrent_get_and_reset(self):
        """並行 get / reset でレースが起きない（状態は idle か running のいずれかの一貫した状態）。"""
        mgr = JobStateManager(_idle, _running)

        def _get():
            for _ in range(20):
                s = mgr.get("generated")
                assert s.status in ("idle", "running")

        def _reset():
            for _ in range(20):
                mgr.reset("generated")

        threads = [threading.Thread(target=_get) for _ in range(5)] + \
                  [threading.Thread(target=_reset) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 最終状態は running（reset が後に呼ばれていれば）
        assert mgr.get("generated").status in ("idle", "running")
