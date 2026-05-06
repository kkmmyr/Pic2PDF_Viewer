"""
routers.generate のユニットテスト。

PDF 生成ジョブ起動・進捗取得・状態一覧・一括圧縮を検証する。
`scan_and_generate` は重い処理なのでモック化してジョブのライフサイクルだけ追う。

実行方法:
    cd backend
    uv run pytest tests/test_router_generate.py -v
"""
import sys
import os
import time
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.pdf_generator import GenerateResult


# ---------------------------------------------------------------------------
# POST /api/generate
# ---------------------------------------------------------------------------

class TestGenerate:
    def test_invalid_source_dir_returns_400(self, client, tmp_data_dir):
        res = client.post("/api/generate", json={"source_dir": "/nope/does/not/exist/qwerty"})
        assert res.status_code == 400

    def test_returns_job_id_and_pending(self, client, tmp_data_dir, monkeypatch):
        # scan_and_generate を即終了するモックに差し替え
        monkeypatch.setattr(
            "routers.generate.scan_and_generate",
            lambda *a, **kw: GenerateResult(generated=[], failed_items=[]),
        )

        src = os.path.join(tmp_data_dir["root"], "src")
        os.makedirs(src)

        res = client.post("/api/generate", json={"source_dir": src})
        assert res.status_code == 200
        body = res.json()
        assert "job_id" in body
        assert body["status"] == "pending"

    def test_initial_genre_written_to_meta(self, client, tmp_data_dir, monkeypatch):
        """新規生成された PDF に genre: "オリジナル" が初期書き込みされる。"""
        monkeypatch.setattr(
            "routers.generate.scan_and_generate",
            lambda *a, **kw: GenerateResult(generated=["new1.pdf", "new2.pdf"], failed_items=[]),
        )

        src = os.path.join(tmp_data_dir["root"], "src")
        os.makedirs(src)

        res = client.post("/api/generate", json={"source_dir": src})
        job_id = res.json()["job_id"]

        # ジョブ完了を待つ
        for _ in range(50):
            r = client.get(f"/api/generate/job/{job_id}")
            if r.json()["status"] == "completed":
                break
            time.sleep(0.05)
        assert r.json()["status"] == "completed"

        meta_path = os.path.join(tmp_data_dir["DATA_DIR"], "meta", "generated", "meta.json")
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["new1.pdf"]["genre"] == "オリジナル"
        assert meta["new2.pdf"]["genre"] == "オリジナル"

    def test_existing_meta_genre_preserved(self, client, tmp_data_dir, monkeypatch):
        """既存メタデータがある書籍には genre を上書きしない。"""
        meta_dir = os.path.join(tmp_data_dir["DATA_DIR"], "meta", "generated")
        os.makedirs(meta_dir, exist_ok=True)
        with open(os.path.join(meta_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"existing.pdf": {"genre": "プリンセスコネクト", "authors": ["A"]}}, f)

        monkeypatch.setattr(
            "routers.generate.scan_and_generate",
            lambda *a, **kw: GenerateResult(generated=["existing.pdf"], failed_items=[]),
        )

        src = os.path.join(tmp_data_dir["root"], "src")
        os.makedirs(src)

        res = client.post("/api/generate", json={"source_dir": src})
        job_id = res.json()["job_id"]
        for _ in range(50):
            if client.get(f"/api/generate/job/{job_id}").json()["status"] == "completed":
                break
            time.sleep(0.05)

        with open(os.path.join(meta_dir, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["existing.pdf"]["genre"] == "プリンセスコネクト"
        assert meta["existing.pdf"]["authors"] == ["A"]

    def test_failed_job_records_error(self, client, tmp_data_dir, monkeypatch):
        def _boom(*a, **kw):
            raise RuntimeError("boom!")
        monkeypatch.setattr("routers.generate.scan_and_generate", _boom)

        src = os.path.join(tmp_data_dir["root"], "src")
        os.makedirs(src)

        res = client.post("/api/generate", json={"source_dir": src})
        job_id = res.json()["job_id"]
        for _ in range(50):
            r = client.get(f"/api/generate/job/{job_id}").json()
            if r["status"] == "failed":
                break
            time.sleep(0.05)
        assert r["status"] == "failed"
        assert "boom" in r["error"]

    def test_failed_items_message(self, client, tmp_data_dir, monkeypatch):
        monkeypatch.setattr(
            "routers.generate.scan_and_generate",
            lambda *a, **kw: GenerateResult(
                generated=["ok.pdf"],
                failed_items=[("bad.zip", "Corrupt zip")],
            ),
        )
        src = os.path.join(tmp_data_dir["root"], "src")
        os.makedirs(src)

        res = client.post("/api/generate", json={"source_dir": src})
        job_id = res.json()["job_id"]
        for _ in range(50):
            r = client.get(f"/api/generate/job/{job_id}").json()
            if r["status"] == "completed":
                break
            time.sleep(0.05)
        assert "1 succeeded" in r["message"]
        assert "1 failed" in r["message"]


# ---------------------------------------------------------------------------
# GET /api/generate/job/{job_id}
# ---------------------------------------------------------------------------

class TestGetGenerateJob:
    def test_404_for_unknown_job(self, client, tmp_data_dir):
        res = client.get("/api/generate/job/nonexistent-uuid")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_empty_for_missing_dir(self, client, tmp_data_dir):
        res = client.get("/api/status?source_dir=/nope/qwerty/zzz")
        assert res.status_code == 200
        assert res.json() == {"items": []}

    def test_lists_folders_with_webp(self, client, tmp_data_dir, make_webp):
        src = os.path.join(tmp_data_dir["root"], "src")
        make_webp(os.path.join(src, "alpha", "1.webp"))
        make_webp(os.path.join(src, "beta", "1.webp"))

        res = client.get(f"/api/status?source_dir={src}")
        items = res.json()["items"]
        names = {(it["name"], it["type"]) for it in items}
        assert ("alpha", "folder") in names
        assert ("beta", "folder") in names

    def test_status_completed_when_images_exist(self, client, tmp_data_dir, make_webp):
        src = os.path.join(tmp_data_dir["root"], "src")
        make_webp(os.path.join(src, "alpha", "1.webp"))
        # IMAGES_DIR/alpha/ にファイルがあれば completed
        make_webp(os.path.join(tmp_data_dir["IMAGES_DIR"], "alpha", "1.webp"))

        res = client.get(f"/api/status?source_dir={src}")
        items = res.json()["items"]
        alpha = next(it for it in items if it["name"] == "alpha")
        assert alpha["status"] == "completed"

    def test_status_not_started_when_no_images(self, client, tmp_data_dir, make_webp):
        src = os.path.join(tmp_data_dir["root"], "src")
        make_webp(os.path.join(src, "newone", "1.webp"))

        res = client.get(f"/api/status?source_dir={src}")
        items = res.json()["items"]
        item = next(it for it in items if it["name"] == "newone")
        assert item["status"] == "not_started"


# ---------------------------------------------------------------------------
# POST /api/batch_compress
# ---------------------------------------------------------------------------

class TestBatchCompress:
    def test_invokes_batch_compress(self, client, tmp_data_dir, monkeypatch):
        called = {}

        def _fake(images_dir, out_dir, quality, **kw):
            called["images_dir"] = images_dir
            called["out_dir"] = out_dir
            called["quality"] = quality
            return ["alpha/alpha.pdf"]

        monkeypatch.setattr("routers.generate.batch_compress", _fake)

        res = client.post("/api/batch_compress", json={"quality": 70})
        assert res.status_code == 200
        assert res.json()["files"] == ["alpha/alpha.pdf"]
        assert called["quality"] == 70

    def test_404_when_images_dir_missing(self, client, tmp_data_dir, monkeypatch):
        # IMAGES_DIR を消す
        import shutil
        shutil.rmtree(tmp_data_dir["IMAGES_DIR"])

        res = client.post("/api/batch_compress", json={"quality": 50})
        assert res.status_code == 404
