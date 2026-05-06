"""
services.series_resolver のユニットテスト。

ルールベースのシリーズ判定（タイトル前方一致 + 巻数パターン）の挙動を確認する。

実行方法:
    cd backend
    uv run pytest tests/test_series.py -v
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.series_detector import (
    common_prefix as _common_prefix,
)
from services.series_detector import (
    detect_series_in_group as _detect_series_in_group,
)
from services.series_resolver import (
    get_state,
    reset_state,
    run_resolve,
)

# 巻数パーサーのテストは tests/test_volume_parser.py に移動済み（Phase 21）


# ---------------------------------------------------------------------------
# _common_prefix
# ---------------------------------------------------------------------------

class TestCommonPrefix:
    def test_basic(self):
        assert _common_prefix("鬼滅の刃 1", "鬼滅の刃 2") == "鬼滅の刃 "

    def test_no_overlap(self):
        assert _common_prefix("hello", "world") == ""

    def test_full_overlap(self):
        assert _common_prefix("same", "same") == "same"


# ---------------------------------------------------------------------------
# _detect_series_in_group — グループ内のシリーズ検出
# ---------------------------------------------------------------------------

class TestDetectSeriesInGroup:
    def test_simple_series(self):
        # 「鬼滅の刃 1」「鬼滅の刃 2」「鬼滅の刃 3」 → 全部シリーズ化
        group = [
            ("", "鬼滅の刃 1.pdf", "鬼滅の刃 1"),
            ("", "鬼滅の刃 2.pdf", "鬼滅の刃 2"),
            ("", "鬼滅の刃 3.pdf", "鬼滅の刃 3"),
        ]
        result = _detect_series_in_group(group)
        assert len(result) == 3
        # series_title は trim 済みプレフィックス
        for _key, (title, _idx) in result.items():
            assert title == "鬼滅の刃"
        # 各 index が 1, 2, 3 になっている
        indices = sorted(idx for _, (_, idx) in result.items())
        assert indices == [1, 2, 3]

    def test_short_prefix_excluded(self):
        # 「ab1」「ab2」 → 共通プレフィックス「ab」が短いので除外
        group = [
            ("", "ab1.pdf", "ab1"),
            ("", "ab2.pdf", "ab2"),
        ]
        result = _detect_series_in_group(group)
        assert result == {}

    def test_non_volume_suffix_excluded(self):
        # 「進撃の巨人 1」「進撃の巨人 外伝」 → 後者の残部分が巻数パターンでない → ペアとして判定されない
        group = [
            ("", "進撃の巨人 1.pdf", "進撃の巨人 1"),
            ("", "進撃の巨人 外伝.pdf", "進撃の巨人 外伝"),
        ]
        result = _detect_series_in_group(group)
        assert result == {}

    def test_singleton_excluded(self):
        # 1冊だけならシリーズ化しない
        group = [("", "ぼっち本 1.pdf", "ぼっち本 1")]
        result = _detect_series_in_group(group)
        assert result == {}

    def test_mixed_patterns(self):
        # 「ABCDE 1」「ABCDE 第2巻」「ABCDE vol.3」混合
        group = [
            ("", "ABCDE 1.pdf",      "ABCDE 1"),
            ("", "ABCDE 第2巻.pdf",  "ABCDE 第2巻"),
            ("", "ABCDE vol.3.pdf",  "ABCDE vol.3"),
        ]
        result = _detect_series_in_group(group)
        assert len(result) == 3

    def test_fractional_volume_included(self):
        """「タイトル 2」と「タイトル 2.5」は同シリーズ判定（小数巻対応）"""
        group = [
            ("", "ABCDEFG 1.pdf",   "ABCDEFG 1"),
            ("", "ABCDEFG 2.pdf",   "ABCDEFG 2"),
            ("", "ABCDEFG 2.5.pdf", "ABCDEFG 2.5"),
        ]
        result = _detect_series_in_group(group)
        # 3 冊全部メンバーになる
        assert len(result) == 3
        indices = sorted(idx for _, (_, idx) in result.items())
        assert indices == [1.0, 2.0, 2.5]

    def test_no_volume_first_book_treated_as_one(self):
        """「タイトル」（巻数なし）と「タイトル2」のペア → 前者を 1 巻扱い"""
        group = [
            ("", "ABCDEFG.pdf",  "ABCDEFG"),
            ("", "ABCDEFG2.pdf", "ABCDEFG2"),
            ("", "ABCDEFG3.pdf", "ABCDEFG3"),
        ]
        result = _detect_series_in_group(group)
        assert len(result) == 3
        # ABCDEFG.pdf に 1.0、ABCDEFG2.pdf に 2.0、ABCDEFG3.pdf に 3.0
        idx_by_key = {k: idx for k, (_, idx) in result.items()}
        assert idx_by_key["ABCDEFG.pdf"] == 1.0
        assert idx_by_key["ABCDEFG2.pdf"] == 2.0
        assert idx_by_key["ABCDEFG3.pdf"] == 3.0

    def test_no_volume_alone_not_detected(self):
        """巻数なし 1 冊だけではシリーズ化しない"""
        group = [
            ("", "ABCDEFG.pdf",  "ABCDEFG"),
            ("", "ABCDEFG1.pdf", "ABCDEFG1"),
        ]
        # 「タイトル」と「タイトル1」のペアはルールから除外される（1巻同士で曖昧）
        result = _detect_series_in_group(group)
        assert result == {}


# ---------------------------------------------------------------------------
# run_resolve（end-to-end）
# ---------------------------------------------------------------------------

@pytest.fixture
def series_env(tmp_path, monkeypatch):
    """run_resolve を tmp_path 配下で動かす環境を作る。"""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    monkeypatch.setattr("config.PDF_COMPRESSED_DIR", str(pdf_dir))
    monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
    return tmp_path, pdf_dir


def _read_meta(tmp_path, source: str = "generated") -> dict:
    p = tmp_path / "meta" / source / "meta.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _seed_meta(tmp_path, entries: dict, source: str = "generated") -> None:
    meta_dir = tmp_path / "meta" / source
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "meta.json").write_text(json.dumps(entries), encoding="utf-8")


class TestRunResolve:
    def test_groups_books_by_author_and_prefix(self, series_env):
        tmp_path, pdf_dir = series_env

        # 同作者・シリーズと同作者・別シリーズと別作者・シリーズを混在させる
        for name in (
            "鬼滅の刃 1.pdf", "鬼滅の刃 2.pdf",
            "進撃の巨人 1.pdf", "進撃の巨人 2.pdf",
            "別本.pdf",
        ):
            (pdf_dir / name).write_bytes(b"")

        _seed_meta(tmp_path, {
            "鬼滅の刃 1.pdf":   {"authors": ["A"]},
            "鬼滅の刃 2.pdf":   {"authors": ["A"]},
            "進撃の巨人 1.pdf": {"authors": ["B"]},
            "進撃の巨人 2.pdf": {"authors": ["B"]},
            "別本.pdf":         {"authors": ["A"]},  # 単独
        })

        reset_state("generated")
        run_resolve("generated")

        meta = _read_meta(tmp_path)
        # 鬼滅の刃ペアは同じ series_id を持つ
        assert meta["鬼滅の刃 1.pdf"]["series_id"] == meta["鬼滅の刃 2.pdf"]["series_id"]
        assert meta["鬼滅の刃 1.pdf"]["series_title"] == "鬼滅の刃"
        assert meta["鬼滅の刃 1.pdf"]["series_index"] == 1
        assert meta["鬼滅の刃 2.pdf"]["series_index"] == 2
        # 進撃の巨人は別作者なので別 series_id
        assert meta["進撃の巨人 1.pdf"]["series_id"] != meta["鬼滅の刃 1.pdf"]["series_id"]
        # 単独本はシリーズ化されない
        assert "series_id" not in meta["別本.pdf"]

        state = get_state("generated")
        assert state.status == "done"
        assert state.created == 2  # 2 シリーズ作成された

    def test_clears_existing_series_on_rerun(self, series_env):
        tmp_path, pdf_dir = series_env

        (pdf_dir / "Old A 1.pdf").write_bytes(b"")
        # 既存の series_id がある状態で run → 単独本になり series_* が消えるはず
        _seed_meta(tmp_path, {
            "Old A 1.pdf": {
                "authors": ["A"],
                "series_id": "stale123",
                "series_title": "Old",
                "series_index": 1,
            },
        })

        reset_state("generated")
        run_resolve("generated")

        meta = _read_meta(tmp_path)
        assert "series_id" not in meta["Old A 1.pdf"]
        assert "series_title" not in meta["Old A 1.pdf"]
        assert "series_index" not in meta["Old A 1.pdf"]

    def test_skips_books_without_authors(self, series_env):
        tmp_path, pdf_dir = series_env

        (pdf_dir / "Foobar 1.pdf").write_bytes(b"")
        (pdf_dir / "Foobar 2.pdf").write_bytes(b"")
        # authors が空 → 作者グループに含まれずシリーズ化対象外
        _seed_meta(tmp_path, {
            "Foobar 1.pdf": {"authors": []},
            "Foobar 2.pdf": {"authors": []},
        })

        reset_state("generated")
        run_resolve("generated")

        meta = _read_meta(tmp_path)
        assert "series_id" not in meta["Foobar 1.pdf"]
        assert "series_id" not in meta["Foobar 2.pdf"]

    def test_preserves_other_fields(self, series_env):
        tmp_path, pdf_dir = series_env

        (pdf_dir / "Series 1.pdf").write_bytes(b"")
        (pdf_dir / "Series 2.pdf").write_bytes(b"")
        _seed_meta(tmp_path, {
            "Series 1.pdf": {
                "authors": ["A"],
                "tags": ["タグ1"],
                "view_count": 5,
                "last_viewed_at": 1700000000.0,
            },
            "Series 2.pdf": {"authors": ["A"]},
        })

        reset_state("generated")
        run_resolve("generated")

        meta = _read_meta(tmp_path)
        # シリーズ化されつつ他フィールドが残る
        assert meta["Series 1.pdf"]["series_id"] == meta["Series 2.pdf"]["series_id"]
        assert meta["Series 1.pdf"]["tags"] == ["タグ1"]
        assert meta["Series 1.pdf"]["view_count"] == 5
        assert meta["Series 1.pdf"]["last_viewed_at"] == 1700000000.0


# ---------------------------------------------------------------------------
# Gemma 補助（Phase 2）
# ---------------------------------------------------------------------------

class TestGemmaAugmentation:
    def test_yes_response_adds_to_existing_series(self, series_env, monkeypatch):
        """Gemma が YES と答えた書籍は既存シリーズに追加される。"""
        tmp_path, pdf_dir = series_env

        # 同作者の「鬼滅の刃 1」「鬼滅の刃 2」と「鬼滅の刃 外伝」
        for name in ("鬼滅の刃 1.pdf", "鬼滅の刃 2.pdf", "鬼滅の刃 外伝.pdf"):
            (pdf_dir / name).write_bytes(b"")
        _seed_meta(tmp_path, {
            "鬼滅の刃 1.pdf":   {"authors": ["A"]},
            "鬼滅の刃 2.pdf":   {"authors": ["A"]},
            "鬼滅の刃 外伝.pdf": {"authors": ["A"]},
        })

        # Gemma を YES だけ返すモック関数に差し替え
        def fake_call(prompt, source="series_resolver"):
            return "YES"
        monkeypatch.setattr(
            "services.series_resolver.import_ollama_client",
            lambda: fake_call,
        )

        reset_state("generated")
        run_resolve("generated", use_gemma=True)

        meta = _read_meta(tmp_path)
        # 外伝も series_id が付与されて既存シリーズに合流する
        assert meta["鬼滅の刃 外伝.pdf"]["series_id"] == meta["鬼滅の刃 1.pdf"]["series_id"]
        # series_index は max+1 = 3 になる
        assert meta["鬼滅の刃 外伝.pdf"]["series_index"] == 3

    def test_no_response_keeps_unassigned(self, series_env, monkeypatch):
        """Gemma が NO と答えた書籍はシリーズ未割当のまま。"""
        tmp_path, pdf_dir = series_env

        for name in ("鬼滅の刃 1.pdf", "鬼滅の刃 2.pdf", "進撃の巨人.pdf"):
            (pdf_dir / name).write_bytes(b"")
        _seed_meta(tmp_path, {
            "鬼滅の刃 1.pdf": {"authors": ["A"]},
            "鬼滅の刃 2.pdf": {"authors": ["A"]},
            "進撃の巨人.pdf": {"authors": ["A"]},
        })

        def fake_call(prompt, source="series_resolver"):
            return "NO"
        monkeypatch.setattr(
            "services.series_resolver.import_ollama_client",
            lambda: fake_call,
        )

        reset_state("generated")
        run_resolve("generated", use_gemma=True)

        meta = _read_meta(tmp_path)
        # 進撃の巨人はシリーズ未割当のまま
        assert "series_id" not in meta["進撃の巨人.pdf"]

    def test_gemma_unavailable_does_not_error(self, series_env, monkeypatch):
        """Gemma クライアントが取得できなくてもジョブ自体は成功する。"""
        tmp_path, pdf_dir = series_env

        for name in ("Some Book 1.pdf", "Some Book 2.pdf"):
            (pdf_dir / name).write_bytes(b"")
        _seed_meta(tmp_path, {
            "Some Book 1.pdf": {"authors": ["A"]},
            "Some Book 2.pdf": {"authors": ["A"]},
        })

        # Gemma クライアントがインポート不可な状況を模擬
        monkeypatch.setattr(
            "services.series_resolver.import_ollama_client",
            lambda: None,
        )

        reset_state("generated")
        run_resolve("generated", use_gemma=True)

        # ルール判定だけは通って、シリーズ化されている
        meta = _read_meta(tmp_path)
        assert meta["Some Book 1.pdf"]["series_id"] == meta["Some Book 2.pdf"]["series_id"]
        state = get_state("generated")
        assert state.status == "done"

    def test_use_gemma_false_does_not_call(self, series_env, monkeypatch):
        """use_gemma=False のとき Gemma クライアントは呼ばれない。"""
        tmp_path, pdf_dir = series_env

        (pdf_dir / "Book A 1.pdf").write_bytes(b"")
        (pdf_dir / "Book A 2.pdf").write_bytes(b"")
        _seed_meta(tmp_path, {
            "Book A 1.pdf": {"authors": ["A"]},
            "Book A 2.pdf": {"authors": ["A"]},
        })

        called = []
        def fake_ensure():
            called.append(True)
            return None
        monkeypatch.setattr("services.series_resolver.import_ollama_client", fake_ensure)

        reset_state("generated")
        run_resolve("generated", use_gemma=False)

        assert called == []  # 一度も呼ばれない


# ---------------------------------------------------------------------------
# 手動編集 API（assign / unassign）
# ---------------------------------------------------------------------------

@pytest.fixture
def series_client(tmp_path, monkeypatch):
    """assign / unassign を検証する TestClient。`meta_store.DATA_DIR` を tmp_path に。"""
    from fastapi.testclient import TestClient
    monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
    from main import app
    return TestClient(app), tmp_path


def _read_meta_at(tmp_path, source: str = "generated") -> dict:
    p = tmp_path / "meta" / source / "meta.json"
    return json.loads(p.read_text(encoding="utf-8"))


class TestAssignSeries:
    def test_new_series_generates_id(self, series_client):
        client, tmp_path = series_client
        # 先に authors を登録（series_id 自動生成のため）
        client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["A"], "source": "generated",
        })
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "テストシリーズ", "index": 1.0, "source": "generated",
        })
        assert res.status_code == 200
        body = res.json()
        assert body["updated_count"] == 1
        assert body["id"]  # 自動生成された

        meta = _read_meta_at(tmp_path)
        assert meta["book.pdf"]["series_id"] == body["id"]
        assert meta["book.pdf"]["series_title"] == "テストシリーズ"
        assert meta["book.pdf"]["series_index"] == 1.0

    def test_existing_id_reused_for_multiple_books(self, series_client):
        client, tmp_path = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["a.pdf", "b.pdf"], "authors": ["A"], "source": "generated",
        })
        # 1 冊目を新規シリーズに登録
        res1 = client.post("/api/series/assign", json={
            "path": "", "names": ["a.pdf"],
            "title": "X", "index": 1.0, "source": "generated",
        })
        sid = res1.json()["id"]
        # 2 冊目を同じ id で追加
        res2 = client.post("/api/series/assign", json={
            "path": "", "names": ["b.pdf"],
            "title": "X", "index": 2.0, "id": sid, "source": "generated",
        })
        assert res2.status_code == 200
        assert res2.json()["id"] == sid

        meta = _read_meta_at(tmp_path)
        assert meta["a.pdf"]["series_id"] == sid
        assert meta["b.pdf"]["series_id"] == sid
        assert meta["a.pdf"]["series_index"] == 1.0
        assert meta["b.pdf"]["series_index"] == 2.0

    def test_assign_preserves_other_fields(self, series_client):
        client, tmp_path = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["A"], "tags": ["t1"], "source": "generated",
        })
        client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "S", "index": 2.5, "source": "generated",
        })

        meta = _read_meta_at(tmp_path)
        assert meta["book.pdf"]["authors"] == ["A"]
        assert meta["book.pdf"]["tags"] == ["t1"]
        assert meta["book.pdf"]["view_count"] == 1
        assert meta["book.pdf"]["series_index"] == 2.5

    def test_assign_supports_fractional_index(self, series_client):
        client, tmp_path = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["A"], "source": "generated",
        })
        client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "Z", "index": 4.5, "source": "generated",
        })
        meta = _read_meta_at(tmp_path)
        assert meta["book.pdf"]["series_index"] == 4.5

    def test_assign_invalid_source_returns_400(self, series_client):
        client, _ = series_client
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "X", "index": 1.0, "source": "invalid",
        })
        assert res.status_code == 400

    def test_assign_empty_title_returns_400(self, series_client):
        client, _ = series_client
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "  ", "index": 1.0, "source": "generated",
        })
        assert res.status_code == 400

    def test_assign_index_array_per_book(self, series_client):
        """index を配列で渡すと names[i] に index[i] が割り当てられる。"""
        client, tmp_path = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["a.pdf", "b.pdf", "c.pdf"],
            "authors": ["A"], "source": "generated",
        })
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["a.pdf", "b.pdf", "c.pdf"],
            "title": "Z", "index": [1.0, 2.0, 3.0], "source": "generated",
        })
        assert res.status_code == 200
        assert res.json()["updated_count"] == 3
        meta = _read_meta_at(tmp_path)
        assert meta["a.pdf"]["series_index"] == 1.0
        assert meta["b.pdf"]["series_index"] == 2.0
        assert meta["c.pdf"]["series_index"] == 3.0
        # 全部同じ series_id
        assert meta["a.pdf"]["series_id"] == meta["b.pdf"]["series_id"] == meta["c.pdf"]["series_id"]

    def test_assign_index_array_length_mismatch_returns_400(self, series_client):
        client, _ = series_client
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["a.pdf", "b.pdf"],
            "title": "Z", "index": [1.0, 2.0, 3.0], "source": "generated",
        })
        assert res.status_code == 400

    def test_assign_index_scalar_still_applies_to_all(self, series_client):
        """後方互換: index が単一 number なら全 names に同じ巻数を割り当て。"""
        client, tmp_path = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["a.pdf", "b.pdf"],
            "authors": ["A"], "source": "generated",
        })
        res = client.post("/api/series/assign", json={
            "path": "", "names": ["a.pdf", "b.pdf"],
            "title": "Z", "index": 5.0, "source": "generated",
        })
        assert res.status_code == 200
        meta = _read_meta_at(tmp_path)
        assert meta["a.pdf"]["series_index"] == 5.0
        assert meta["b.pdf"]["series_index"] == 5.0


class TestUnassignSeries:
    def test_unassign_removes_series_fields(self, series_client):
        client, tmp_path = series_client
        client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["A"], "source": "generated",
        })
        client.post("/api/series/assign", json={
            "path": "", "names": ["book.pdf"],
            "title": "S", "index": 1.0, "source": "generated",
        })
        client.post("/api/series/unassign", json={
            "path": "", "names": ["book.pdf"], "source": "generated",
        })
        meta = _read_meta_at(tmp_path)
        # series_* は消えるが authors は残る
        assert "series_id" not in meta["book.pdf"]
        assert "series_title" not in meta["book.pdf"]
        assert "series_index" not in meta["book.pdf"]
        assert meta["book.pdf"]["authors"] == ["A"]

    def test_unassign_no_existing_entry_is_noop(self, series_client):
        client, _ = series_client
        # メタなし状態で unassign してもエラーにならない
        res = client.post("/api/series/unassign", json={
            "path": "", "names": ["nothere.pdf"], "source": "generated",
        })
        assert res.status_code == 200
        assert res.json()["updated_count"] == 1


class TestReorderSeries:
    def _setup_series(self, client, names: list[str]) -> str:
        """3 冊を 1 つのシリーズに登録し、series_id を返すヘルパー。"""
        client.patch("/api/meta", json={
            "path": "", "names": names, "authors": ["A"], "source": "generated",
        })
        res = client.post("/api/series/assign", json={
            "path": "", "names": names,
            "title": "S", "index": [float(i + 1) for i in range(len(names))],
            "source": "generated",
        })
        return res.json()["id"]

    def test_reorder_renumbers_in_given_order(self, series_client):
        client, tmp_path = series_client
        sid = self._setup_series(client, ["a.pdf", "b.pdf", "c.pdf"])
        res = client.post("/api/series/reorder", json={
            "path": "", "names": ["c.pdf", "a.pdf", "b.pdf"],
            "series_id": sid, "source": "generated",
        })
        assert res.status_code == 200
        assert res.json()["updated_count"] == 3

        meta = _read_meta_at(tmp_path)
        assert meta["c.pdf"]["series_index"] == 1.0
        assert meta["a.pdf"]["series_index"] == 2.0
        assert meta["b.pdf"]["series_index"] == 3.0

    def test_reorder_preserves_other_fields(self, series_client):
        client, tmp_path = series_client
        sid = self._setup_series(client, ["a.pdf", "b.pdf"])
        client.post("/api/meta/view", json={
            "path": "", "name": "a.pdf", "source": "generated",
        })
        client.post("/api/series/reorder", json={
            "path": "", "names": ["b.pdf", "a.pdf"],
            "series_id": sid, "source": "generated",
        })
        meta = _read_meta_at(tmp_path)
        assert meta["a.pdf"]["authors"] == ["A"]
        assert meta["a.pdf"]["view_count"] == 1
        assert meta["a.pdf"]["series_id"] == sid
        assert meta["a.pdf"]["series_title"] == "S"

    def test_reorder_rejects_book_from_different_series(self, series_client):
        client, tmp_path = series_client
        sid = self._setup_series(client, ["a.pdf", "b.pdf"])
        # 別シリーズの c.pdf を作成
        client.patch("/api/meta", json={
            "path": "", "names": ["c.pdf"], "authors": ["B"], "source": "generated",
        })
        client.post("/api/series/assign", json={
            "path": "", "names": ["c.pdf"],
            "title": "Other", "index": 1.0, "source": "generated",
        })
        # series_id 不一致で 400
        res = client.post("/api/series/reorder", json={
            "path": "", "names": ["a.pdf", "c.pdf"],
            "series_id": sid, "source": "generated",
        })
        assert res.status_code == 400
        # 失敗時は元の順序が保たれる（中途半端な書き込みなし）
        meta = _read_meta_at(tmp_path)
        assert meta["a.pdf"]["series_index"] == 1.0
        assert meta["b.pdf"]["series_index"] == 2.0

    def test_reorder_empty_names_returns_400(self, series_client):
        client, _ = series_client
        res = client.post("/api/series/reorder", json={
            "path": "", "names": [], "series_id": "x", "source": "generated",
        })
        assert res.status_code == 400

    def test_reorder_invalid_source_returns_400(self, series_client):
        client, _ = series_client
        res = client.post("/api/series/reorder", json={
            "path": "", "names": ["a.pdf"], "series_id": "x", "source": "invalid",
        })
        assert res.status_code == 400
