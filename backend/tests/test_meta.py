"""
services.meta_store / routers.meta のユニットテスト。

実行方法:
    cd backend
    uv run pytest tests/test_meta.py -v
"""
import json
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.meta_store import make_key


class TestMakeKey:
    def test_with_path(self):
        assert make_key("sub/dir", "book.pdf") == "sub/dir/book.pdf"

    def test_empty_path(self):
        assert make_key("", "book.pdf") == "book.pdf"

    def test_nested_path(self):
        assert make_key("a/b/c", "x.pdf") == "a/b/c/x.pdf"


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


def _read_meta(tmp_path, source: str = "doujin") -> dict:
    p = tmp_path / "meta" / source / "meta.json"
    return json.loads(p.read_text(encoding="utf-8"))


class TestRecordView:
    def test_first_view_increments_to_one(self, view_client, tmp_path):
        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
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
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        body = res.json()
        # 5 分以内の再閲覧は連打抑制でカウント据え置き
        assert body["view_count"] == 1
        assert body["incremented"] is False

    def test_recall_after_debounce_increments(self, view_client, tmp_path):
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        # last_viewed_at を 6 分前に書き換えて連打抑制閾値（5分）超過状態を作る
        meta_path = tmp_path / "meta" / "doujin" / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["book.pdf"]["last_viewed_at"] = time.time() - 360
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        body = res.json()
        assert body["view_count"] == 2
        assert body["incremented"] is True

    def test_last_viewed_at_always_updates(self, view_client, tmp_path):
        """連打抑制でカウント据え置きでも last_viewed_at は更新される（最近見た順ソート用）。"""
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        first = _read_meta(tmp_path)["book.pdf"]["last_viewed_at"]
        time.sleep(0.05)  # 微小だが計測可能な差を作る
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        second = _read_meta(tmp_path)["book.pdf"]["last_viewed_at"]
        assert second > first

    def test_preserves_authors(self, view_client, tmp_path):
        # 作者名を先に登録
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["サークルA"], "source": "doujin",
        })
        # 閲覧記録
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["authors"] == ["サークルA"]
        assert meta["book.pdf"]["view_count"] == 1

    def test_invalid_source_rejected(self, view_client):
        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "invalid",
        })
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /api/meta — 作者更新時の view_count 保持
# ---------------------------------------------------------------------------

class TestUpdateAuthorsPreservesViewCount:
    def test_update_authors_preserves_view_count(self, view_client, tmp_path):
        # 閲覧記録 → 作者を後から付与
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["サークルA"], "source": "doujin",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["authors"] == ["サークルA"]
        assert meta["book.pdf"]["view_count"] == 1
        assert meta["book.pdf"]["last_viewed_at"] > 0

    def test_clear_authors_keeps_view_count(self, view_client, tmp_path):
        # 作者あり + 閲覧記録 → 作者を空にする
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["サークルA"], "source": "doujin",
        })
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": [], "source": "doujin",
        })
        meta = _read_meta(tmp_path)
        # authors=[] になり、view_count は保持される
        assert meta["book.pdf"]["authors"] == []
        assert meta["book.pdf"]["view_count"] == 1

    def test_clear_authors_removes_entry_if_no_other_fields(self, view_client, tmp_path):
        # 作者のみのエントリで authors を空にすると、エントリごと削除
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["サークルA"], "source": "doujin",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": [], "source": "doujin",
        })
        meta = _read_meta(tmp_path)
        assert "book.pdf" not in meta


# ---------------------------------------------------------------------------
# PATCH /api/meta — 入力バリデーション
# ---------------------------------------------------------------------------

class TestUpdateMetaValidation:
    def test_no_field_specified_returns_400(self, view_client):
        """authors/hidden/genre/read_state すべて省略すると 400。"""
        res = view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "source": "doujin",
        })
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /api/meta — 非表示フラグ
# ---------------------------------------------------------------------------

class TestUpdateHidden:
    def test_hidden_true_sets_flag(self, view_client, tmp_path):
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": True, "source": "doujin",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["hidden"] is True

    def test_hidden_false_removes_flag(self, view_client, tmp_path):
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": True, "source": "doujin",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": False, "source": "doujin",
        })
        meta = _read_meta(tmp_path)
        # hidden=False で再表示 → エントリは他フィールドが無いので削除
        assert "book.pdf" not in meta

    def test_hidden_preserves_authors(self, view_client, tmp_path):
        # authors を登録
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"],
            "authors": ["A"], "source": "doujin",
        })
        # hidden=true のみ送る
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": True, "source": "doujin",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["authors"] == ["A"]
        assert meta["book.pdf"]["hidden"] is True

    def test_hidden_preserves_view_count(self, view_client, tmp_path):
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": True, "source": "doujin",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["view_count"] == 1
        assert meta["book.pdf"]["hidden"] is True

    def test_hidden_unhide_keeps_other_fields(self, view_client, tmp_path):
        # authors + hidden を登録
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"],
            "authors": ["A"], "hidden": True, "source": "doujin",
        })
        # hidden=false で再表示
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": False, "source": "doujin",
        })
        meta = _read_meta(tmp_path)
        # authors は残る、hidden だけ消える
        assert meta["book.pdf"]["authors"] == ["A"]
        assert "hidden" not in meta["book.pdf"]

    def test_hidden_only_request_is_accepted(self, view_client):
        """hidden だけ指定したリクエストは authors 省略でも 200 を返す。"""
        res = view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": True, "source": "doujin",
        })
        assert res.status_code == 200

    def test_bulk_hide_multiple_books(self, view_client, tmp_path):
        res = view_client.patch("/api/meta", json={
            "path": "", "names": ["a.pdf", "b.pdf", "c.pdf"],
            "hidden": True, "source": "doujin",
        })
        assert res.status_code == 200
        assert res.json()["updated_count"] == 3
        meta = _read_meta(tmp_path)
        for n in ("a.pdf", "b.pdf", "c.pdf"):
            assert meta[n]["hidden"] is True


# ---------------------------------------------------------------------------
# read_state — 自動遷移と手動操作
# ---------------------------------------------------------------------------

class TestReadStateAutoTransition:
    def test_first_view_sets_reading(self, view_client, tmp_path):
        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        assert res.json()["read_state"] == "reading"
        assert _read_meta(tmp_path)["book.pdf"]["read_state"] == "reading"

    def test_debounced_view_does_not_change_state(self, view_client, tmp_path):
        # 1 回目で reading になる → 直後の連打は据え置き（reading のまま）
        view_client.post("/api/meta/view", json={"path": "", "name": "book.pdf", "source": "doujin"})
        # 手動で done に上げる
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "read_state": "done", "source": "doujin",
        })
        # 連打抑制中（5 分以内）に再閲覧しても read_state は据え置き＝done のまま
        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        assert res.json()["incremented"] is False
        assert res.json()["read_state"] == "done"
        assert _read_meta(tmp_path)["book.pdf"]["read_state"] == "done"

    def test_done_is_preserved_on_increment(self, view_client, tmp_path):
        """連打抑制を抜けた再閲覧でも done は維持される（読了済み書籍の再読）。"""
        view_client.post("/api/meta/view", json={"path": "", "name": "book.pdf", "source": "doujin"})
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "read_state": "done", "source": "doujin",
        })
        # last_viewed_at を 6 分前に巻き戻して連打抑制を外す
        meta_path = tmp_path / "meta" / "doujin" / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["book.pdf"]["last_viewed_at"] = time.time() - 360
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        res = view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        assert res.json()["incremented"] is True
        assert res.json()["read_state"] == "done"
        assert _read_meta(tmp_path)["book.pdf"]["read_state"] == "done"


class TestReadStateManualUpdate:
    def test_set_done_via_patch(self, view_client, tmp_path):
        res = view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "read_state": "done", "source": "doujin",
        })
        assert res.status_code == 200
        assert _read_meta(tmp_path)["book.pdf"]["read_state"] == "done"

    def test_clear_via_empty_string(self, view_client, tmp_path):
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "read_state": "done", "source": "doujin",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "read_state": "", "source": "doujin",
        })
        # 他フィールドが無いのでエントリごと消える（has_meaningful_value=False）
        assert "book.pdf" not in _read_meta(tmp_path)

    def test_invalid_read_state_returns_400(self, view_client):
        res = view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "read_state": "finished", "source": "doujin",
        })
        assert res.status_code == 400

    def test_read_state_only_request_is_accepted(self, view_client):
        """read_state だけ指定したリクエストは authors/hidden/genre 省略でも 200。"""
        res = view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "read_state": "reading", "source": "doujin",
        })
        assert res.status_code == 200

    def test_read_state_preserves_view_count(self, view_client, tmp_path):
        view_client.post("/api/meta/view", json={"path": "", "name": "book.pdf", "source": "doujin"})
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "read_state": "done", "source": "doujin",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["view_count"] == 1
        assert meta["book.pdf"]["read_state"] == "done"


