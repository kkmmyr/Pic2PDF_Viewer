"""
services.meta_store / services.auto_fill_service / routers.meta のユニットテスト。

実行方法:
    cd backend
    uv run pytest tests/test_meta.py -v
"""
import sys
import os
import json
import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.meta_store import make_key
from services.auto_fill_service import _is_missing, _is_unknown


class TestMakeKey:
    def test_with_path(self):
        assert make_key("sub/dir", "book.pdf") == "sub/dir/book.pdf"

    def test_empty_path(self):
        assert make_key("", "book.pdf") == "book.pdf"

    def test_nested_path(self):
        assert make_key("a/b/c", "x.pdf") == "a/b/c/x.pdf"


class TestIsMissing:
    def test_key_not_in_meta(self):
        assert _is_missing({}, "missing.pdf") is True

    def test_empty_authors(self):
        meta = {"book.pdf": {"authors": []}}
        assert _is_missing(meta, "book.pdf") is True

    def test_with_real_author(self):
        meta = {"book.pdf": {"authors": ["サークルA"]}}
        assert _is_missing(meta, "book.pdf") is False

    def test_unknown_author_not_missing(self):
        # 「作者不明」は登録済みなので missing ではない
        meta = {"book.pdf": {"authors": ["作者不明"]}}
        assert _is_missing(meta, "book.pdf") is False


class TestIsUnknown:
    def test_unknown_author(self):
        meta = {"book.pdf": {"authors": ["作者不明"]}}
        assert _is_unknown(meta, "book.pdf") is True

    def test_real_author_not_unknown(self):
        meta = {"book.pdf": {"authors": ["サークルA"]}}
        assert _is_unknown(meta, "book.pdf") is False

    def test_empty_authors_not_unknown(self):
        meta = {"book.pdf": {"authors": []}}
        assert _is_unknown(meta, "book.pdf") is False

    def test_key_not_in_meta(self):
        assert _is_unknown({}, "missing.pdf") is False

    def test_multiple_authors_with_unknown(self):
        # ["作者不明", "Author2"] は完全一致しないので unknown ではない
        meta = {"book.pdf": {"authors": ["作者不明", "Author2"]}}
        assert _is_unknown(meta, "book.pdf") is False


# ---------------------------------------------------------------------------
# POST /api/meta/view — 閲覧記録 + 連打抑制
# ---------------------------------------------------------------------------

@pytest.fixture
def view_client(tmp_path, monkeypatch):
    """meta_store の DATA_DIR を tmp_path に差し替えた TestClient を提供する。"""
    monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
    # FastAPI app をテスト用にインポート（DATA_DIR 差し替え後）
    from main import app
    return TestClient(app)


def _read_meta(tmp_path, source: str = "generated") -> dict:
    p = tmp_path / "meta" / source / "meta.json"
    return json.loads(p.read_text(encoding="utf-8"))


class TestRecordView:
    def test_first_view_increments_to_one(self, view_client, tmp_path):
        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        assert res.status_code == 200
        body = res.json()
        assert body["view_count"] == 1
        assert body["incremented"] is True
        assert body["last_viewed_at"] > 0
        # ディスクにも反映されている
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["view_count"] == 1

    def test_immediate_recall_does_not_increment(self, view_client):
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        body = res.json()
        # 5 分以内の再閲覧は連打抑制でカウント据え置き
        assert body["view_count"] == 1
        assert body["incremented"] is False

    def test_recall_after_debounce_increments(self, view_client, tmp_path):
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        # last_viewed_at を 6 分前に書き換えて連打抑制閾値（5分）超過状態を作る
        meta_path = tmp_path / "meta" / "generated" / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["book.pdf"]["last_viewed_at"] = time.time() - 360
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        body = res.json()
        assert body["view_count"] == 2
        assert body["incremented"] is True

    def test_last_viewed_at_always_updates(self, view_client, tmp_path):
        """連打抑制でカウント据え置きでも last_viewed_at は更新される（最近見た順ソート用）。"""
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        first = _read_meta(tmp_path)["book.pdf"]["last_viewed_at"]
        time.sleep(0.05)  # 微小だが計測可能な差を作る
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        second = _read_meta(tmp_path)["book.pdf"]["last_viewed_at"]
        assert second > first

    def test_preserves_authors(self, view_client, tmp_path):
        # 作者名を先に登録
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["サークルA"], "source": "generated",
        })
        # 閲覧記録
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["authors"] == ["サークルA"]
        assert meta["book.pdf"]["view_count"] == 1

    def test_invalid_source_rejected(self, view_client):
        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "invalid",
        })
        assert res.status_code == 400
