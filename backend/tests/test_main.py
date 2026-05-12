"""
main のユニットテスト。

例外ハンドラ・CORS・SPA フォールバックを検証する。

実行方法:
    cd backend
    uv run pytest tests/test_main.py -v
"""
import os
import sys

from fastapi import APIRouter

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# 例外ハンドラ
# ---------------------------------------------------------------------------

class TestExceptionHandlers:
    """各カスタム例外がハンドラ経由で適切な status / detail に変換されるか。"""

    def test_file_operation_error_returns_500(self, client):
        from exceptions import FileOperationError
        from main import app

        # テスト専用ルーターを動的に追加
        router = APIRouter()

        @router.post("/api/__test_file_op_error")
        def _raise():
            raise FileOperationError("disk full")

        app.include_router(router)
        try:
            res = client.post("/api/__test_file_op_error")
            assert res.status_code == 500
            assert "disk full" in res.json()["detail"]
        finally:
            # クリーンアップ: 追加したルートを除去
            app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/api/__test_file_op_error"]

    def test_ocr_process_error_returns_400(self, client):
        from exceptions import OcrProcessError
        from main import app

        router = APIRouter()

        @router.post("/api/__test_ocr_error")
        def _raise():
            raise OcrProcessError("ocr stopped")

        app.include_router(router)
        try:
            res = client.post("/api/__test_ocr_error")
            assert res.status_code == 400
            assert "ocr stopped" in res.json()["detail"]
        finally:
            app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/api/__test_ocr_error"]


    def test_unhandled_exception_masked_as_500(self, tmp_data_dir):
        """未捕捉例外は status=500 / detail="Internal server error" にマスクされる。"""
        from fastapi.testclient import TestClient

        from main import app

        router = APIRouter()

        @router.post("/api/__test_unhandled")
        def _raise():
            raise KeyError("internal-detail-leak")

        app.include_router(router)
        # raise_server_exceptions=False で例外ハンドラの動作を確認できる
        client = TestClient(app, raise_server_exceptions=False)
        try:
            res = client.post("/api/__test_unhandled")
            assert res.status_code == 500
            assert res.json()["detail"] == "Internal server error"
            # 内部詳細が漏れていない
            assert "internal-detail-leak" not in res.json()["detail"]
        finally:
            app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/api/__test_unhandled"]


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

class TestCors:
    def test_options_returns_cors_headers(self, client):
        """プリフライトリクエストで CORS ヘッダが付く。"""
        res = client.options(
            "/api/meta",
            headers={
                "Origin": "http://localhost:5176",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS ミドルウェアが処理して 200 を返す
        assert res.status_code in (200, 204)
        assert "access-control-allow-origin" in {k.lower() for k in res.headers.keys()}


# ---------------------------------------------------------------------------
# 静的マウントの存在
# ---------------------------------------------------------------------------

class TestStaticMounts:
    def test_thumbnails_mount_present(self):
        """/thumbnails と /images が StaticFiles でマウントされている。"""
        from main import app
        mount_paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/thumbnails" in mount_paths
        assert "/images" in mount_paths

    def test_kindle_mounts_present(self):
        from main import app
        mount_paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/comic/pdfs" in mount_paths
        assert "/comic/thumbnails" in mount_paths

    def test_routers_registered(self):
        """各 router が /api プレフィクスで登録されている。"""
        from main import app
        api_paths = [r.path for r in app.routes if hasattr(r, "path") and r.path.startswith("/api/")]
        # 主要エンドポイントが含まれる
        joined = " ".join(api_paths)
        assert "/api/pdfs" in joined
        assert "/api/meta" in joined
        assert "/api/genres" in joined
        assert "/api/series" in joined
