"""
routers.series（手動編集 API）のユニットテスト。

`POST /api/series/assign` / `POST /api/series/unassign` / `POST /api/series/reorder`
の HTTP 層を検証する。シリーズ自動グループ化は撤去済み（2026-05-09、Phase 6）。

実行方法:
    cd backend
    uv run pytest tests/test_series.py -v
"""
import pytest

from services.meta_store import load_meta

# ---------------------------------------------------------------------------
# 手動編集 API（assign / unassign）
# ---------------------------------------------------------------------------

@pytest.fixture
def series_client(tmp_path, monkeypatch):
    """assign / unassign を検証する TestClient。`config.META_DB_DIR` を tmp_path に。"""
    import config
    from fastapi.testclient import TestClient
    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path))
    from main import app
    return TestClient(app)


def _read_meta(source: str = "doujin") -> dict:
    return load_meta(source)


class TestAssignSeries:
    def test_new_series_generates_id(self, series_client):
        client = series_client
        # 先に authors を登録（series_id 自動生成のため）
        client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["A"], "source": "doujin",
        })
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "テストシリーズ", "index": 1.0, "source": "doujin",
        })
        assert res.status_code == 200
        body = res.json()
        assert body["updated_count"] == 1
        assert body["id"]  # 自動生成された

        meta = _read_meta()
        assert meta["book.pdf"]["series_id"] == body["id"]
        assert meta["book.pdf"]["series_title"] == "テストシリーズ"
        assert meta["book.pdf"]["series_index"] == 1.0

    def test_existing_id_reused_for_multiple_books(self, series_client):
        client = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["a.pdf", "b.pdf"], "authors": ["A"], "source": "doujin",
        })
        # 1 冊目を新規シリーズに登録
        res1 = client.post("/api/series/assign", json={
            "path": "", "names": ["a.pdf"],
            "title": "X", "index": 1.0, "source": "doujin",
        })
        sid = res1.json()["id"]
        # 2 冊目を同じ id で追加
        res2 = client.post("/api/series/assign", json={
            "path": "", "names": ["b.pdf"],
            "title": "X", "index": 2.0, "id": sid, "source": "doujin",
        })
        assert res2.status_code == 200
        assert res2.json()["id"] == sid

        meta = _read_meta()
        assert meta["a.pdf"]["series_id"] == sid
        assert meta["b.pdf"]["series_id"] == sid
        assert meta["a.pdf"]["series_index"] == 1.0
        assert meta["b.pdf"]["series_index"] == 2.0

    def test_assign_preserves_other_fields(self, series_client):
        client = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["A"], "source": "doujin",
        })
        client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "doujin",
        })
        client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "S", "index": 2.5, "source": "doujin",
        })

        meta = _read_meta()
        assert meta["book.pdf"]["authors"] == ["A"]
        assert meta["book.pdf"]["view_count"] == 1
        assert meta["book.pdf"]["series_index"] == 2.5

    def test_assign_supports_fractional_index(self, series_client):
        client = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["A"], "source": "doujin",
        })
        client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "Z", "index": 4.5, "source": "doujin",
        })
        meta = _read_meta()
        assert meta["book.pdf"]["series_index"] == 4.5

    def test_assign_invalid_source_returns_400(self, series_client):
        client = series_client
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "X", "index": 1.0, "source": "invalid",
        })
        assert res.status_code == 400

    def test_assign_empty_title_returns_400(self, series_client):
        client = series_client
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "  ", "index": 1.0, "source": "doujin",
        })
        assert res.status_code == 400

    def test_assign_index_array_per_book(self, series_client):
        """index を配列で渡すと names[i] に index[i] が割り当てられる。"""
        client = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["a.pdf", "b.pdf", "c.pdf"],
            "authors": ["A"], "source": "doujin",
        })
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["a.pdf", "b.pdf", "c.pdf"],
            "title": "Z", "index": [1.0, 2.0, 3.0], "source": "doujin",
        })
        assert res.status_code == 200
        assert res.json()["updated_count"] == 3
        meta = _read_meta()
        assert meta["a.pdf"]["series_index"] == 1.0
        assert meta["b.pdf"]["series_index"] == 2.0
        assert meta["c.pdf"]["series_index"] == 3.0
        # 全部同じ series_id
        assert meta["a.pdf"]["series_id"] == meta["b.pdf"]["series_id"] == meta["c.pdf"]["series_id"]

    def test_assign_index_array_length_mismatch_returns_400(self, series_client):
        client = series_client
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["a.pdf", "b.pdf"],
            "title": "Z", "index": [1.0, 2.0, 3.0], "source": "doujin",
        })
        assert res.status_code == 400

    def test_assign_index_scalar_still_applies_to_all(self, series_client):
        """後方互換: index が単一 number なら全 names に同じ巻数を割り当て。"""
        client = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["a.pdf", "b.pdf"],
            "authors": ["A"], "source": "doujin",
        })
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["a.pdf", "b.pdf"],
            "title": "Z", "index": 5.0, "source": "doujin",
        })
        assert res.status_code == 200
        meta = _read_meta()
        assert meta["a.pdf"]["series_index"] == 5.0
        assert meta["b.pdf"]["series_index"] == 5.0


class TestUnassignSeries:
    def test_unassign_removes_series_fields(self, series_client):
        client = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["A"], "source": "doujin",
        })
        client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "S", "index": 1.0, "source": "doujin",
        })
        client.post("/api/series/unassign", json={
            "path": "", "names": ["book.pdf"], "source": "doujin",
        })
        meta = _read_meta()
        # series_* は消えるが authors は残る
        assert "series_id" not in meta["book.pdf"]
        assert "series_title" not in meta["book.pdf"]
        assert "series_index" not in meta["book.pdf"]
        assert meta["book.pdf"]["authors"] == ["A"]

    def test_unassign_no_existing_entry_is_noop(self, series_client):
        client = series_client
        # メタなし状態で unassign してもエラーにならない
        res = client.post("/api/series/unassign", json={
            "path": "", "names": ["nothere.pdf"], "source": "doujin",
        })
        assert res.status_code == 200
        assert res.json()["updated_count"] == 1


class TestReorderSeries:
    def _setup_series(self, client, names: list[str]) -> str:
        """3 冊を 1 つのシリーズに登録し、series_id を返すヘルパー。"""
        client.patch("/api/meta", json={
            "path": "", "names": names, "authors": ["A"], "source": "doujin",
        })
        res = client.post("/api/series/assign", json={
            "path": "", "names": names,
            "title": "S", "index": [float(i + 1) for i in range(len(names))],
            "source": "doujin",
        })
        return res.json()["id"]

    def test_reorder_renumbers_in_given_order(self, series_client):
        client = series_client
        sid = self._setup_series(client, ["a.pdf", "b.pdf", "c.pdf"])
        res = client.post("/api/series/reorder", json={
            "path": "", "names": ["c.pdf", "a.pdf", "b.pdf"],
            "series_id": sid, "source": "doujin",
        })
        assert res.status_code == 200
        assert res.json()["updated_count"] == 3

        meta = _read_meta()
        assert meta["c.pdf"]["series_index"] == 1.0
        assert meta["a.pdf"]["series_index"] == 2.0
        assert meta["b.pdf"]["series_index"] == 3.0

    def test_reorder_preserves_other_fields(self, series_client):
        client = series_client
        sid = self._setup_series(client, ["a.pdf", "b.pdf"])
        client.post("/api/meta/view", json={
            "path": "", "name": "a.pdf", "source": "doujin",
        })
        client.post("/api/series/reorder", json={
            "path": "", "names": ["b.pdf", "a.pdf"],
            "series_id": sid, "source": "doujin",
        })
        meta = _read_meta()
        assert meta["a.pdf"]["authors"] == ["A"]
        assert meta["a.pdf"]["view_count"] == 1
        assert meta["a.pdf"]["series_id"] == sid
        assert meta["a.pdf"]["series_title"] == "S"

    def test_reorder_rejects_book_from_different_series(self, series_client):
        client = series_client
        sid = self._setup_series(client, ["a.pdf", "b.pdf"])
        # 別シリーズの c.pdf を作成
        client.patch("/api/meta", json={
            "path": "", "names": ["c.pdf"], "authors": ["B"], "source": "doujin",
        })
        client.post("/api/series/assign", json={
            "path": "", "names": ["c.pdf"],
            "title": "Other", "index": 1.0, "source": "doujin",
        })
        # series_id 不一致で 400
        res = client.post("/api/series/reorder", json={
            "path": "", "names": ["a.pdf", "c.pdf"],
            "series_id": sid, "source": "doujin",
        })
        assert res.status_code == 400
        # 失敗時は元の順序が保たれる（中途半端な書き込みなし）
        meta = _read_meta()
        assert meta["a.pdf"]["series_index"] == 1.0
        assert meta["b.pdf"]["series_index"] == 2.0

    def test_reorder_empty_names_returns_400(self, series_client):
        client = series_client
        res = client.post("/api/series/reorder", json={
            "path": "", "names": [], "series_id": "x", "source": "doujin",
        })
        assert res.status_code == 400

    def test_reorder_invalid_source_returns_400(self, series_client):
        client = series_client
        res = client.post("/api/series/reorder", json={
            "path": "", "names": ["a.pdf"], "series_id": "x", "source": "invalid",
        })
        assert res.status_code == 400
