"""services.hitomi.state_store のユニットテスト。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.hitomi.state_store import (
    load_state,
    save_state,
)


class TestStateLoadSave:
    def test_load_returns_default_when_no_file(self, tmp_path):
        state = load_state(tmp_path)
        assert state["last_run_status"] == "never"
        assert state["last_run_at"] is None
        assert state["artists"] == {}

    def test_save_then_load_roundtrip(self, tmp_path):
        save_state(
            tmp_path,
            {
                "last_run_at": "2026-04-29T03:00:00+09:00",
                "last_run_status": "ok",
                "last_error": None,
                "artists": {"aka_shio:japanese": {"top_id": 100, "checked_at": "x"}},
            },
        )
        loaded = load_state(tmp_path)
        assert loaded["last_run_status"] == "ok"
        assert loaded["artists"]["aka_shio:japanese"]["top_id"] == 100
