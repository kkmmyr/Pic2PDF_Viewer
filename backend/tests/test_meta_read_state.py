"""Read-state transition tests for the meta API."""

import time

import pytest
from fastapi.testclient import TestClient

from services.meta_store import load_meta, update_meta_locked


@pytest.fixture
def view_client(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path))
    from main import app

    return TestClient(app)


def _read_meta(source: str = "doujin") -> dict:
    return load_meta(source)


# ---------------------------------------------------------------------------
# read_state — 自動遷移と手動操作
# ---------------------------------------------------------------------------


class TestReadStateAutoTransition:
    def test_first_view_sets_reading(self, view_client):
        res = view_client.post(
            "/api/meta/view",
            json={
                "path": "",
                "name": "book.pdf",
                "source": "doujin",
            },
        )
        assert res.json()["read_state"] == "reading"
        assert _read_meta()["book.pdf"]["read_state"] == "reading"

    def test_debounced_view_does_not_change_state(self, view_client):
        view_client.post("/api/meta/view", json={"path": "", "name": "book.pdf", "source": "doujin"})
        view_client.patch(
            "/api/meta",
            json={
                "path": "",
                "names": ["book.pdf"],
                "read_state": "done",
                "source": "doujin",
            },
        )
        res = view_client.post(
            "/api/meta/view",
            json={
                "path": "",
                "name": "book.pdf",
                "source": "doujin",
            },
        )
        assert res.json()["incremented"] is False
        assert res.json()["read_state"] == "done"
        assert _read_meta()["book.pdf"]["read_state"] == "done"

    def test_done_is_preserved_on_increment(self, view_client):
        """連打抑制を抜けた再閲覧でも done は維持される（読了済み書籍の再読）。"""
        view_client.post("/api/meta/view", json={"path": "", "name": "book.pdf", "source": "doujin"})
        view_client.patch(
            "/api/meta",
            json={
                "path": "",
                "names": ["book.pdf"],
                "read_state": "done",
                "source": "doujin",
            },
        )
        update_meta_locked("doujin", lambda d: d["book.pdf"].update({"last_viewed_at": time.time() - 360}))

        res = view_client.post(
            "/api/meta/view",
            json={
                "path": "",
                "name": "book.pdf",
                "source": "doujin",
            },
        )
        assert res.json()["incremented"] is True
        assert res.json()["read_state"] == "done"
        assert _read_meta()["book.pdf"]["read_state"] == "done"


class TestReadStateManualUpdate:
    def test_set_done_via_patch(self, view_client):
        res = view_client.patch(
            "/api/meta",
            json={
                "path": "",
                "names": ["book.pdf"],
                "read_state": "done",
                "source": "doujin",
            },
        )
        assert res.status_code == 200
        assert _read_meta()["book.pdf"]["read_state"] == "done"

    def test_clear_via_empty_string(self, view_client):
        view_client.patch(
            "/api/meta",
            json={
                "path": "",
                "names": ["book.pdf"],
                "read_state": "done",
                "source": "doujin",
            },
        )
        view_client.patch(
            "/api/meta",
            json={
                "path": "",
                "names": ["book.pdf"],
                "read_state": "",
                "source": "doujin",
            },
        )
        assert "book.pdf" not in _read_meta()

    def test_invalid_read_state_returns_400(self, view_client):
        res = view_client.patch(
            "/api/meta",
            json={
                "path": "",
                "names": ["book.pdf"],
                "read_state": "finished",
                "source": "doujin",
            },
        )
        assert res.status_code == 400

    def test_read_state_only_request_is_accepted(self, view_client):
        res = view_client.patch(
            "/api/meta",
            json={
                "path": "",
                "names": ["book.pdf"],
                "read_state": "reading",
                "source": "doujin",
            },
        )
        assert res.status_code == 200

    def test_read_state_preserves_view_count(self, view_client):
        view_client.post("/api/meta/view", json={"path": "", "name": "book.pdf", "source": "doujin"})
        view_client.patch(
            "/api/meta",
            json={
                "path": "",
                "names": ["book.pdf"],
                "read_state": "done",
                "source": "doujin",
            },
        )
        meta = _read_meta()
        assert meta["book.pdf"]["view_count"] == 1
        assert meta["book.pdf"]["read_state"] == "done"
