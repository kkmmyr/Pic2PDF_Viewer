"""
routers.meta の追補ユニットテスト。

`test_meta.py` でカバーされていない以下を検証する:
- GET  /api/meta
- GET  /api/meta/export
- PATCH /api/meta の genre フィールド・空 list 削除挙動

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


