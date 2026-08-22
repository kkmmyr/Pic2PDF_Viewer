"""hitomi監視のprocess間lockを実ファイルで検証する。"""

import pytest

from services.hitomi.process_lock import MonitorAlreadyRunningError, monitor_process_lock


def test_second_lock_is_rejected_while_first_is_held(tmp_path):
    with monitor_process_lock(tmp_path):
        with pytest.raises(MonitorAlreadyRunningError):
            with monitor_process_lock(tmp_path):
                pass


def test_lock_can_be_reacquired_after_release(tmp_path):
    with monitor_process_lock(tmp_path):
        pass

    with monitor_process_lock(tmp_path):
        assert (tmp_path / "monitor.lock").exists()
