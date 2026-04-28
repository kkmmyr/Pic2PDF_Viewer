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


# ---------------------------------------------------------------------------
# PATCH /api/meta — 作者更新時の view_count 保持
# ---------------------------------------------------------------------------

class TestUpdateAuthorsPreservesViewCount:
    def test_update_authors_preserves_view_count(self, view_client, tmp_path):
        # 閲覧記録 → 作者を後から付与
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["サークルA"], "source": "generated",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["authors"] == ["サークルA"]
        assert meta["book.pdf"]["view_count"] == 1
        assert meta["book.pdf"]["last_viewed_at"] > 0

    def test_clear_authors_keeps_view_count(self, view_client, tmp_path):
        # 作者あり + 閲覧記録 → 作者を空にする
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["サークルA"], "source": "generated",
        })
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": [], "source": "generated",
        })
        meta = _read_meta(tmp_path)
        # authors=[] になり、view_count は保持される
        assert meta["book.pdf"]["authors"] == []
        assert meta["book.pdf"]["view_count"] == 1

    def test_clear_authors_removes_entry_if_no_other_fields(self, view_client, tmp_path):
        # 作者のみのエントリで authors を空にすると、エントリごと削除
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["サークルA"], "source": "generated",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": [], "source": "generated",
        })
        meta = _read_meta(tmp_path)
        assert "book.pdf" not in meta


# ---------------------------------------------------------------------------
# PATCH /api/meta — タグ機能
# ---------------------------------------------------------------------------

class TestUpdateTags:
    def test_tags_only_create(self, view_client, tmp_path):
        res = view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "tags": ["ジャンル1", "気分A"], "source": "generated",
        })
        assert res.status_code == 200
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["tags"] == ["ジャンル1", "気分A"]
        # authors は省略されたので存在しない
        assert "authors" not in meta["book.pdf"]

    def test_authors_only_does_not_clear_tags(self, view_client, tmp_path):
        # 先に tags を登録
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "tags": ["ジャンル1"], "source": "generated",
        })
        # authors のみを後から登録（tags は省略）
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["サークルA"], "source": "generated",
        })
        meta = _read_meta(tmp_path)
        # tags は保持される
        assert meta["book.pdf"]["tags"] == ["ジャンル1"]
        assert meta["book.pdf"]["authors"] == ["サークルA"]

    def test_tags_only_does_not_clear_authors(self, view_client, tmp_path):
        # 先に authors を登録
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "authors": ["サークルA"], "source": "generated",
        })
        # tags のみを後から登録
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "tags": ["ジャンル1"], "source": "generated",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["authors"] == ["サークルA"]
        assert meta["book.pdf"]["tags"] == ["ジャンル1"]

    def test_tags_preserves_view_count(self, view_client, tmp_path):
        # 閲覧記録 → tags 更新で view_count が保持される
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "tags": ["ジャンル1"], "source": "generated",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["view_count"] == 1
        assert meta["book.pdf"]["tags"] == ["ジャンル1"]

    def test_clear_tags_keeps_authors(self, view_client, tmp_path):
        # authors + tags を登録
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"],
            "authors": ["サークルA"], "tags": ["ジャンル1"], "source": "generated",
        })
        # tags を空配列で削除
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "tags": [], "source": "generated",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["authors"] == ["サークルA"]
        # tags は空配列で残る
        assert meta["book.pdf"].get("tags") == []

    def test_clear_both_removes_entry(self, view_client, tmp_path):
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"],
            "authors": ["サークルA"], "tags": ["ジャンル1"], "source": "generated",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"],
            "authors": [], "tags": [], "source": "generated",
        })
        meta = _read_meta(tmp_path)
        # 両方空かつ閲覧履歴も無い → エントリごと削除
        assert "book.pdf" not in meta

    def test_neither_authors_nor_tags_returns_400(self, view_client):
        res = view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "source": "generated",
        })
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /api/meta — 非表示フラグ
# ---------------------------------------------------------------------------

class TestUpdateHidden:
    def test_hidden_true_sets_flag(self, view_client, tmp_path):
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": True, "source": "generated",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["hidden"] is True

    def test_hidden_false_removes_flag(self, view_client, tmp_path):
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": True, "source": "generated",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": False, "source": "generated",
        })
        meta = _read_meta(tmp_path)
        # hidden=False で再表示 → エントリは他フィールドが無いので削除
        assert "book.pdf" not in meta

    def test_hidden_preserves_authors_and_tags(self, view_client, tmp_path):
        # authors + tags を登録
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"],
            "authors": ["A"], "tags": ["t1"], "source": "generated",
        })
        # hidden=true のみ送る
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": True, "source": "generated",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["authors"] == ["A"]
        assert meta["book.pdf"]["tags"] == ["t1"]
        assert meta["book.pdf"]["hidden"] is True

    def test_hidden_preserves_view_count(self, view_client, tmp_path):
        view_client.post("/api/meta/view", json={
            "path": "", "name": "book.pdf", "source": "generated",
        })
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": True, "source": "generated",
        })
        meta = _read_meta(tmp_path)
        assert meta["book.pdf"]["view_count"] == 1
        assert meta["book.pdf"]["hidden"] is True

    def test_hidden_unhide_keeps_other_fields(self, view_client, tmp_path):
        # authors + hidden を登録
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"],
            "authors": ["A"], "hidden": True, "source": "generated",
        })
        # hidden=false で再表示
        view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": False, "source": "generated",
        })
        meta = _read_meta(tmp_path)
        # authors は残る、hidden だけ消える
        assert meta["book.pdf"]["authors"] == ["A"]
        assert "hidden" not in meta["book.pdf"]

    def test_hidden_only_request_is_accepted(self, view_client):
        """hidden だけ指定したリクエストは authors/tags 省略でも 200 を返す。"""
        res = view_client.patch("/api/meta", json={
            "path": "", "names": ["book.pdf"], "hidden": True, "source": "generated",
        })
        assert res.status_code == 200

    def test_bulk_hide_multiple_books(self, view_client, tmp_path):
        res = view_client.patch("/api/meta", json={
            "path": "", "names": ["a.pdf", "b.pdf", "c.pdf"],
            "hidden": True, "source": "generated",
        })
        assert res.status_code == 200
        assert res.json()["updated_count"] == 3
        meta = _read_meta(tmp_path)
        for n in ("a.pdf", "b.pdf", "c.pdf"):
            assert meta[n]["hidden"] is True


# ---------------------------------------------------------------------------
# auto_fill_service.run_auto_fill — 既存 view_count / last_viewed_at の保持
# ---------------------------------------------------------------------------

@pytest.fixture
def auto_fill_env(tmp_path, monkeypatch):
    """run_auto_fill を tmp_path 配下で動作させるための環境を整える。"""
    # PDF ディレクトリを tmp_path に差し替え
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    monkeypatch.setattr("config.PDF_DIR", str(pdf_dir))
    monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))

    # ジョブの sleep を無効化（テスト高速化）
    monkeypatch.setattr("services.auto_fill_service.AUTOFILL_REQUEST_DELAY_SEC", 0)

    # resolve_author をモック化（外部 API 呼び出しを回避）
    monkeypatch.setattr(
        "services.auto_fill_service.resolve_author",
        lambda title, source: f"サークル_{title}",
    )

    return tmp_path, pdf_dir


class TestRunAutoFillPreservesViewCount:
    def test_overwrite_all_preserves_view_count(self, auto_fill_env):
        """overwrite_all モードでも既存の view_count / last_viewed_at は保持される。"""
        tmp_path, pdf_dir = auto_fill_env

        # ダミー PDF を作成
        (pdf_dir / "book.pdf").write_bytes(b"")

        # 既存メタデータ（閲覧履歴あり、作者は不明）を準備
        meta_dir = tmp_path / "meta" / "generated"
        meta_dir.mkdir(parents=True)
        existing = {
            "book.pdf": {
                "authors": ["作者不明"],
                "view_count": 5,
                "last_viewed_at": 1700000000.0,
            }
        }
        (meta_dir / "meta.json").write_text(json.dumps(existing), encoding="utf-8")

        from services.auto_fill_service import run_auto_fill, get_auto_fill_state, reset_auto_fill_state
        reset_auto_fill_state("generated")
        run_auto_fill("generated", "overwrite_all")

        meta = _read_meta(tmp_path)
        # authors は更新される
        assert meta["book.pdf"]["authors"] == ["サークル_book"]
        # view_count / last_viewed_at は保持される（バグ修正の検証）
        assert meta["book.pdf"]["view_count"] == 5
        assert meta["book.pdf"]["last_viewed_at"] == 1700000000.0

        state = get_auto_fill_state("generated")
        assert state.status == "done"
        assert state.done == 1

    def test_unknown_only_preserves_view_count(self, auto_fill_env):
        """unknown_only モードで「作者不明」を更新するときも view_count を保持する。"""
        tmp_path, pdf_dir = auto_fill_env
        (pdf_dir / "novel.pdf").write_bytes(b"")

        meta_dir = tmp_path / "meta" / "generated"
        meta_dir.mkdir(parents=True)
        existing = {
            "novel.pdf": {
                "authors": ["作者不明"],
                "view_count": 12,
                "last_viewed_at": 1700001234.5,
            }
        }
        (meta_dir / "meta.json").write_text(json.dumps(existing), encoding="utf-8")

        from services.auto_fill_service import run_auto_fill, reset_auto_fill_state
        reset_auto_fill_state("generated")
        run_auto_fill("generated", "unknown_only")

        meta = _read_meta(tmp_path)
        assert meta["novel.pdf"]["authors"] == ["サークル_novel"]
        assert meta["novel.pdf"]["view_count"] == 12
        assert meta["novel.pdf"]["last_viewed_at"] == 1700001234.5

    def test_missing_only_creates_entry_without_view_count(self, auto_fill_env):
        """missing_only で初登録の書籍は view_count なしで authors のみ設定される。"""
        tmp_path, pdf_dir = auto_fill_env
        (pdf_dir / "fresh.pdf").write_bytes(b"")

        # meta.json なし（完全未登録）
        from services.auto_fill_service import run_auto_fill, reset_auto_fill_state
        reset_auto_fill_state("generated")
        run_auto_fill("generated", "missing_only")

        meta = _read_meta(tmp_path)
        assert meta["fresh.pdf"]["authors"] == ["サークル_fresh"]
        # 閲覧履歴は未記録なのでフィールドも存在しない
        assert "view_count" not in meta["fresh.pdf"]
        assert "last_viewed_at" not in meta["fresh.pdf"]
