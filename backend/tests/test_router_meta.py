"""
routers.meta の追補ユニットテスト。

`test_meta.py` でカバーされていない以下を検証する:
- GET  /api/meta
- GET  /api/meta/export
- PATCH /api/meta の genre フィールド・空 list 削除挙動
- POST /api/meta/auto-fill
- GET  /api/meta/auto-fill/status
- GET  /api/meta/auto-fill/test

実行方法:
    cd backend
    uv run pytest tests/test_router_meta.py -v
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _seed_meta(tmp_data_dir, source: str, data: dict) -> str:
    """meta.json を書き込み、そのパスを返す。"""
    meta_dir = os.path.join(tmp_data_dir["DATA_DIR"], "meta", source)
    os.makedirs(meta_dir, exist_ok=True)
    path = os.path.join(meta_dir, "meta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path


# ---------------------------------------------------------------------------
# GET /api/meta
# ---------------------------------------------------------------------------

class TestGetMeta:
    def test_returns_full_meta(self, client, tmp_data_dir):
        _seed_meta(tmp_data_dir, "generated", {
            "a.pdf": {"authors": ["A"]},
            "b.pdf": {"authors": ["B"], "genre": "G"},
        })

        res = client.get("/api/meta?source=generated")
        assert res.status_code == 200
        body = res.json()
        assert body["a.pdf"]["authors"] == ["A"]
        assert body["b.pdf"]["genre"] == "G"

    def test_returns_empty_dict_when_no_meta(self, client, tmp_data_dir):
        res = client.get("/api/meta?source=kindle")
        assert res.status_code == 200
        assert res.json() == {}

    def test_invalid_source_400(self, client, tmp_data_dir):
        res = client.get("/api/meta?source=invalid")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/meta/export
# ---------------------------------------------------------------------------

class TestExportMeta:
    def test_returns_json_with_attachment_header(self, client, tmp_data_dir):
        _seed_meta(tmp_data_dir, "generated", {"a.pdf": {"authors": ["X"]}})

        res = client.get("/api/meta/export?source=generated")
        assert res.status_code == 200
        # Content-Type は application/json
        assert "application/json" in res.headers["content-type"]
        # Content-Disposition: attachment; filename="meta_generated_YYYYMMDD.json"
        cd = res.headers["content-disposition"]
        assert "attachment" in cd
        assert "meta_generated_" in cd
        assert ".json" in cd

        data = res.json()
        assert data["a.pdf"]["authors"] == ["X"]

    def test_invalid_source_400(self, client, tmp_data_dir):
        res = client.get("/api/meta/export?source=invalid")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /api/meta - genre / 空 list 削除
# ---------------------------------------------------------------------------

class TestUpdateMetaGenre:
    def test_set_genre(self, client, tmp_data_dir):
        _seed_meta(tmp_data_dir, "generated", {"a.pdf": {"authors": ["X"]}})

        res = client.patch("/api/meta", json={
            "path": "",
            "names": ["a.pdf"],
            "genre": "プリンセスコネクト",
            "source": "generated",
        })
        assert res.status_code == 200

        path = os.path.join(tmp_data_dir["DATA_DIR"], "meta", "generated", "meta.json")
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["a.pdf"]["genre"] == "プリンセスコネクト"
        assert meta["a.pdf"]["authors"] == ["X"]

    def test_genre_empty_string_removes_field(self, client, tmp_data_dir):
        _seed_meta(tmp_data_dir, "generated", {"a.pdf": {"genre": "X", "authors": ["A"]}})

        client.patch("/api/meta", json={
            "path": "",
            "names": ["a.pdf"],
            "genre": "",
            "source": "generated",
        })

        path = os.path.join(tmp_data_dir["DATA_DIR"], "meta", "generated", "meta.json")
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        assert "genre" not in meta["a.pdf"]
        assert meta["a.pdf"]["authors"] == ["A"]


class TestUpdateMetaEntryDeletion:
    def test_empty_lists_remove_entry(self, client, tmp_data_dir):
        """authors=[] で他に意味のあるフィールドが無ければエントリ自体が消える。"""
        _seed_meta(tmp_data_dir, "generated", {
            "victim.pdf": {"authors": ["A"]},
            "alive.pdf": {"authors": ["B"]},
        })

        client.patch("/api/meta", json={
            "path": "",
            "names": ["victim.pdf"],
            "authors": [],
            "source": "generated",
        })

        path = os.path.join(tmp_data_dir["DATA_DIR"], "meta", "generated", "meta.json")
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        assert "victim.pdf" not in meta
        assert "alive.pdf" in meta

    def test_empty_lists_keep_entry_with_view_count(self, client, tmp_data_dir):
        """view_count 等 list 以外の意味のあるフィールドが残っていればエントリは保持される。"""
        _seed_meta(tmp_data_dir, "generated", {
            "book.pdf": {"authors": ["A"], "view_count": 5, "last_viewed_at": 1700000000.0},
        })

        client.patch("/api/meta", json={
            "path": "",
            "names": ["book.pdf"],
            "authors": [],
            "source": "generated",
        })

        path = os.path.join(tmp_data_dir["DATA_DIR"], "meta", "generated", "meta.json")
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["book.pdf"]["view_count"] == 5
        assert meta["book.pdf"]["last_viewed_at"] == 1700000000.0
        assert meta["book.pdf"]["authors"] == []

    def test_400_when_no_field_specified(self, client, tmp_data_dir):
        res = client.patch("/api/meta", json={
            "path": "",
            "names": ["a.pdf"],
            "source": "generated",
        })
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/meta/auto-fill
# ---------------------------------------------------------------------------

class TestStartAutoFill:
    def test_starts_with_default_mode(self, client, tmp_data_dir, monkeypatch):
        called = {}

        def _fake_start(source, mode):
            called["source"] = source
            called["mode"] = mode

        monkeypatch.setattr("routers.meta.start_auto_fill_job", _fake_start)
        # 既存ジョブを idle にしておく
        # 簡易: state は running でなければよい — monkeypatch で get を idle 返却

        res = client.post("/api/meta/auto-fill?source=generated")
        assert res.status_code == 200
        body = res.json()
        assert body["started"] is True
        assert body["mode"] == "unknown_only"
        assert called["mode"] == "unknown_only"

    def test_invalid_mode_400(self, client, tmp_data_dir):
        res = client.post("/api/meta/auto-fill?source=generated&mode=invalid")
        assert res.status_code == 400

    def test_409_when_already_running(self, client, tmp_data_dir, monkeypatch):
        class _State:
            status = "running"
            total = 0
            done = 0
            skipped = 0
            current = None
            results = []
            error = None

        monkeypatch.setattr("routers.meta.get_auto_fill_state", lambda src: _State())

        res = client.post("/api/meta/auto-fill?source=generated")
        assert res.status_code == 409


# ---------------------------------------------------------------------------
# GET /api/meta/auto-fill/status
# ---------------------------------------------------------------------------

class TestAutoFillStatus:
    def test_returns_state_fields(self, client, tmp_data_dir, monkeypatch):
        class _State:
            status = "running"
            total = 10
            done = 3
            skipped = 1
            current = "book.pdf"
            results = [{"name": "a.pdf", "author": "A"}]
            error = None

        monkeypatch.setattr("routers.meta.get_auto_fill_state", lambda src: _State())

        res = client.get("/api/meta/auto-fill/status?source=generated")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "running"
        assert body["total"] == 10
        assert body["done"] == 3
        assert body["skipped"] == 1
        assert body["current"] == "book.pdf"
        assert body["results"] == [{"name": "a.pdf", "author": "A"}]


# ---------------------------------------------------------------------------
# GET /api/meta/auto-fill/test
# ---------------------------------------------------------------------------

class TestAutoFillTest:
    def test_returns_resolve_author_debug_payload(self, client, tmp_data_dir, monkeypatch):
        monkeypatch.setattr(
            "routers.meta.resolve_author_debug",
            lambda title, source: {"final": f"author_for_{title}", "steps": []},
        )

        res = client.get("/api/meta/auto-fill/test?title=mybook&source=generated")
        assert res.status_code == 200
        assert res.json()["final"] == "author_for_mybook"
