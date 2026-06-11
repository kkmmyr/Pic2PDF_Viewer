"""
routers.genres のユニットテスト。

ジャンルリスト CRUD のフローを検証する。

実行方法:
    cd backend
    uv run pytest tests/test_router_genres.py -v
"""

from services.genre_store import save_genres


def _seed_genres(source: str, genres: list[str]) -> None:
    save_genres(source, genres)


# ---------------------------------------------------------------------------
# GET /api/genres
# ---------------------------------------------------------------------------


class TestGetGenres:
    def test_returns_list(self, client, tmp_data_dir):
        _seed_genres("doujin", ["A", "B"])
        res = client.get("/api/genres?source=doujin")
        assert res.status_code == 200
        assert res.json() == ["A", "B"]

    def test_returns_empty_when_no_meta(self, client, tmp_data_dir):
        res = client.get("/api/genres?source=comic")
        assert res.status_code == 200
        assert res.json() == []

    def test_invalid_source_400(self, client, tmp_data_dir):
        res = client.get("/api/genres?source=invalid")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/genres
# ---------------------------------------------------------------------------


class TestAddGenre:
    def test_add_new_genre(self, client, tmp_data_dir):
        _seed_genres("doujin", ["A"])
        res = client.post("/api/genres", json={"source": "doujin", "name": "B"})
        assert res.status_code == 200
        assert res.json()["genres"] == ["A", "B"]

    def test_409_when_duplicate(self, client, tmp_data_dir):
        _seed_genres("doujin", ["A"])
        res = client.post("/api/genres", json={"source": "doujin", "name": "A"})
        assert res.status_code == 409

    def test_400_when_empty(self, client, tmp_data_dir):
        res = client.post("/api/genres", json={"source": "doujin", "name": ""})
        assert res.status_code == 400

    def test_400_when_whitespace_only(self, client, tmp_data_dir):
        res = client.post("/api/genres", json={"source": "doujin", "name": "   "})
        assert res.status_code == 400

    def test_strips_whitespace(self, client, tmp_data_dir):
        res = client.post("/api/genres", json={"source": "doujin", "name": "  X  "})
        assert res.status_code == 200
        assert "X" in res.json()["genres"]

    def test_invalid_source_400(self, client, tmp_data_dir):
        res = client.post("/api/genres", json={"source": "invalid", "name": "X"})
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /api/genres/{name}
# ---------------------------------------------------------------------------


class TestDeleteGenre:
    def test_delete_existing(self, client, tmp_data_dir):
        _seed_genres("doujin", ["A", "B", "C"])
        res = client.delete("/api/genres/B?source=doujin")
        assert res.status_code == 200
        assert res.json()["genres"] == ["A", "C"]

    def test_404_when_not_found(self, client, tmp_data_dir):
        _seed_genres("doujin", ["A"])
        res = client.delete("/api/genres/Z?source=doujin")
        assert res.status_code == 404

    def test_invalid_source_400(self, client, tmp_data_dir):
        res = client.delete("/api/genres/X?source=invalid")
        assert res.status_code == 400

    def test_400_when_name_contains_path_traversal(self, client, tmp_data_dir):
        """ジャンル名に '..' が URL エンコードで埋め込まれた場合は 400 で拒否する。"""
        _seed_genres("doujin", ["A"])
        # %2E%2E = '..'
        res = client.delete("/api/genres/%2E%2E?source=doujin")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /api/genres/reorder
# ---------------------------------------------------------------------------


class TestReorderGenres:
    def test_reorder_same_set(self, client, tmp_data_dir):
        _seed_genres("doujin", ["A", "B", "C"])
        res = client.patch(
            "/api/genres/reorder",
            json={
                "source": "doujin",
                "genres": ["C", "A", "B"],
            },
        )
        assert res.status_code == 200
        assert res.json()["genres"] == ["C", "A", "B"]

    def test_400_when_set_mismatch(self, client, tmp_data_dir):
        """既存集合と一致しない（追加・削除がある）場合は 400。"""
        _seed_genres("doujin", ["A", "B", "C"])
        res = client.patch(
            "/api/genres/reorder",
            json={
                "source": "doujin",
                "genres": ["A", "B"],  # C が欠けている
            },
        )
        assert res.status_code == 400

    def test_400_when_extra_item(self, client, tmp_data_dir):
        _seed_genres("doujin", ["A", "B"])
        res = client.patch(
            "/api/genres/reorder",
            json={
                "source": "doujin",
                "genres": ["A", "B", "C"],  # 余分
            },
        )
        assert res.status_code == 400

    def test_invalid_source_400(self, client, tmp_data_dir):
        res = client.patch(
            "/api/genres/reorder",
            json={
                "source": "invalid",
                "genres": [],
            },
        )
        assert res.status_code == 400
