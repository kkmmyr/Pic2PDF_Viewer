"""
services.series_suggester のユニットテスト（A-1）。

ルールベースの紐付け候補スコアリングと、`POST /api/series/suggest`
エンドポイントの HTTP 層を検証する。

実行方法:
    cd backend
    uv run pytest tests/test_series_suggester.py -v
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.series_suggester import (
    SUGGEST_MAX_CANDIDATES,
    SUGGEST_MIN_SCORE,
    _common_prefix_len,
    _strip_volume_suffix,
    suggest_series,
)

# ---------------------------------------------------------------------------
# _common_prefix_len
# ---------------------------------------------------------------------------

class TestCommonPrefixLen:
    def test_basic(self):
        assert _common_prefix_len("鬼滅の刃 1", "鬼滅の刃 2") == len("鬼滅の刃 ")

    def test_no_overlap(self):
        assert _common_prefix_len("hello", "world") == 0

    def test_full_overlap(self):
        assert _common_prefix_len("same", "same") == 4


# ---------------------------------------------------------------------------
# _strip_volume_suffix
# ---------------------------------------------------------------------------

class TestStripVolumeSuffix:
    def test_strip_int(self):
        assert _strip_volume_suffix("鬼滅の刃 1") == "鬼滅の刃"

    def test_strip_kan_with_suffix(self):
        assert _strip_volume_suffix("鬼滅の刃 第3巻") == "鬼滅の刃"

    def test_strip_decimal(self):
        assert _strip_volume_suffix("○○ 2.5") == "○○"

    def test_strip_vol(self):
        assert _strip_volume_suffix("○○ vol.4") == "○○"

    def test_strip_paren(self):
        assert _strip_volume_suffix("○○(上)") == "○○"

    def test_no_suffix(self):
        # 末尾が巻数表記でなければ素通し
        assert _strip_volume_suffix("鬼滅の刃") == "鬼滅の刃"


# ---------------------------------------------------------------------------
# suggest_series
# ---------------------------------------------------------------------------

class TestSuggestSeries:
    def test_empty_meta_returns_empty(self):
        assert suggest_series({}, "", ["book.pdf"]) == []

    def test_empty_names_returns_empty(self):
        meta = {"a.pdf": {"authors": ["A"], "series_id": "s1", "series_title": "X", "series_index": 1}}
        assert suggest_series(meta, "", []) == []

    def test_no_existing_series_returns_empty(self):
        # series_id を持つエントリが無いので候補なし
        meta = {"book.pdf": {"authors": ["A"]}}
        assert suggest_series(meta, "", ["other.pdf"]) == []

    def test_high_score_candidate_returned(self):
        """既存シリーズと共通プレフィックスが高い書籍はスコア上位で返る。"""
        meta = {
            "鬼滅の刃 1.pdf": {
                "authors": ["吾峠呼世晴"],
                "series_id": "s1",
                "series_title": "鬼滅の刃 1",
                "series_index": 1.0,
            },
        }
        result = suggest_series(meta, "", ["鬼滅の刃 2.pdf"])
        assert len(result) == 1
        c = result[0]
        assert c["series_id"] == "s1"
        assert c["score"] >= SUGGEST_MIN_SCORE
        # title_match のみ（書籍に authors が無い → 作者一致なし）
        assert "title_match" in c["reason"]
        assert "author_match" not in c["reason"]

    def test_author_match_bonus(self):
        """作者集合一致でスコアが加点される。"""
        meta = {
            "鬼滅の刃 1.pdf": {
                "authors": ["吾峠呼世晴"],
                "series_id": "s1",
                "series_title": "鬼滅の刃 1",
                "series_index": 1.0,
            },
            "鬼滅の刃 2.pdf": {
                "authors": ["吾峠呼世晴"],  # 既存シリーズの作者と一致
            },
        }
        result = suggest_series(meta, "", ["鬼滅の刃 2.pdf"])
        assert len(result) == 1
        assert "author_match" in result[0]["reason"]

    def test_below_threshold_excluded(self):
        """共通プレフィックスが短い書籍は閾値を下回り除外される。"""
        meta = {
            "鬼滅の刃 1.pdf": {
                "authors": ["A"],
                "series_id": "s1",
                "series_title": "鬼滅の刃 1",
                "series_index": 1.0,
            },
        }
        # 全く違うタイトル
        result = suggest_series(meta, "", ["進撃の巨人.pdf"])
        assert result == []

    def test_max_candidates_capped(self):
        """候補数が SUGGEST_MAX_CANDIDATES を超えないことを確認。"""
        meta = {}
        for i in range(SUGGEST_MAX_CANDIDATES + 3):
            meta[f"プレフィックス{i}.pdf"] = {
                "authors": ["A"],
                "series_id": f"s{i}",
                "series_title": f"プレフィックス{i}",
                "series_index": 1.0,
            }
        result = suggest_series(meta, "", ["プレフィックス候補.pdf"])
        assert len(result) <= SUGGEST_MAX_CANDIDATES

    def test_descending_score_order(self):
        """スコア降順で返却される。"""
        meta = {
            "ABCD 1.pdf": {
                "authors": ["A"],
                "series_id": "s_high",
                "series_title": "ABCD 1",
                "series_index": 1.0,
            },
            "AB 1.pdf": {
                "authors": ["A"],
                "series_id": "s_low",
                "series_title": "AB 1",
                "series_index": 1.0,
            },
        }
        # 「ABCDE.pdf」は ABCD と多く一致、AB と少なく一致
        result = suggest_series(meta, "", ["ABCDE.pdf"])
        assert len(result) >= 1
        # スコア順に並んでいる
        scores = [c["score"] for c in result]
        assert scores == sorted(scores, reverse=True)

    def test_max_index_returned(self):
        """series_max_index に series_index の最大値が入る。"""
        meta = {
            "鬼滅の刃 1.pdf": {
                "authors": ["A"],
                "series_id": "s1",
                "series_title": "鬼滅の刃",
                "series_index": 1.0,
            },
            "鬼滅の刃 5.pdf": {
                "authors": ["A"],
                "series_id": "s1",
                "series_title": "鬼滅の刃",
                "series_index": 5.0,
            },
        }
        result = suggest_series(meta, "", ["鬼滅の刃 6.pdf"])
        assert len(result) == 1
        assert result[0]["series_max_index"] == 5.0


# ---------------------------------------------------------------------------
# POST /api/series/suggest（HTTP 層）
# ---------------------------------------------------------------------------

@pytest.fixture
def suggest_client(tmp_path, monkeypatch):
    """suggest_series_endpoint を検証する TestClient。`meta_store.DATA_DIR` を tmp_path に。"""
    from fastapi.testclient import TestClient
    monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
    from main import app
    return TestClient(app), tmp_path


def _seed_meta(tmp_path, entries: dict, source: str = "doujin") -> None:
    meta_dir = tmp_path / "meta" / source
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "meta.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")


class TestSuggestSeriesEndpoint:
    def test_returns_candidates(self, suggest_client):
        client, tmp_path = suggest_client
        _seed_meta(tmp_path, {
            "鬼滅の刃 1.pdf": {
                "authors": ["A"],
                "series_id": "s1",
                "series_title": "鬼滅の刃",
                "series_index": 1.0,
            },
        })
        res = client.post("/api/series/suggest", json={
            "path": "", "names": ["鬼滅の刃 2.pdf"], "source": "doujin",
        })
        assert res.status_code == 200
        body = res.json()
        assert "candidates" in body
        assert len(body["candidates"]) >= 1
        assert body["candidates"][0]["series_id"] == "s1"

    def test_empty_names_returns_400(self, suggest_client):
        client, _ = suggest_client
        res = client.post("/api/series/suggest", json={
            "path": "", "names": [], "source": "doujin",
        })
        assert res.status_code == 400

    def test_invalid_source_returns_400(self, suggest_client):
        client, _ = suggest_client
        res = client.post("/api/series/suggest", json={
            "path": "", "names": ["a.pdf"], "source": "invalid",
        })
        assert res.status_code == 400

    def test_no_existing_series_returns_empty_list(self, suggest_client):
        client, tmp_path = suggest_client
        _seed_meta(tmp_path, {"book.pdf": {"authors": ["A"]}})
        res = client.post("/api/series/suggest", json={
            "path": "", "names": ["other.pdf"], "source": "doujin",
        })
        assert res.status_code == 200
        assert res.json()["candidates"] == []
