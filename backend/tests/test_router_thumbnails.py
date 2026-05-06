"""
routers.thumbnails のユニットテスト。

ページサムネイルのオンデマンド生成（GET /api/thumbnails/page）と
サムネイル再生成（POST /api/thumbnails/regenerate / regenerate_bulk）を検証する。

実行方法:
    cd backend
    uv run pytest tests/test_router_thumbnails.py -v
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# GET /api/thumbnails/page
# ---------------------------------------------------------------------------

class TestGetPageThumbnail:
    def test_generated_returns_webp_directly(self, client, tmp_data_dir, make_webp):
        img_dir = tmp_data_dir["IMAGES_DIR"]
        make_webp(os.path.join(img_dir, "book", "1.webp"), color=(255, 0, 0))
        make_webp(os.path.join(img_dir, "book", "2.webp"), color=(0, 255, 0))

        res = client.get("/api/thumbnails/page?name=book.pdf&page=1&source=generated")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/webp"
        assert "max-age=3600" in res.headers["cache-control"]

    def test_generated_404_when_no_images(self, client, tmp_data_dir):
        res = client.get("/api/thumbnails/page?name=nope.pdf&page=1&source=generated")
        assert res.status_code == 404

    def test_generated_400_when_page_out_of_range(self, client, tmp_data_dir, make_webp):
        img_dir = tmp_data_dir["IMAGES_DIR"]
        make_webp(os.path.join(img_dir, "book", "1.webp"))

        res = client.get("/api/thumbnails/page?name=book.pdf&page=99&source=generated")
        assert res.status_code == 400

    def test_400_when_page_less_than_1(self, client, tmp_data_dir):
        res = client.get("/api/thumbnails/page?name=book.pdf&page=0&source=generated")
        assert res.status_code == 400

    def test_kindle_renders_pdf_to_jpeg(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "book.pdf"), page_count=3)

        res = client.get("/api/thumbnails/page?name=book.pdf&page=1&source=kindle")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/jpeg"

    def test_kindle_404_when_pdf_missing(self, client, tmp_data_dir):
        res = client.get("/api/thumbnails/page?name=nope.pdf&page=1&source=kindle")
        assert res.status_code == 404

    def test_kindle_400_when_page_out_of_range(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "book.pdf"), page_count=2)

        res = client.get("/api/thumbnails/page?name=book.pdf&page=99&source=kindle")
        assert res.status_code == 400

    def test_invalid_source_returns_400(self, client, tmp_data_dir):
        res = client.get("/api/thumbnails/page?name=book.pdf&page=1&source=invalid")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/thumbnails/regenerate
# ---------------------------------------------------------------------------

class TestRegenerateThumbnail:
    def test_regenerate_from_pdf(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        thumb_dir = tmp_data_dir["KINDLE_THUMBNAIL_DIR"]
        make_pdf(os.path.join(pdf_dir, "book.pdf"))

        res = client.post("/api/thumbnails/regenerate", json={
            "path": "",
            "name": "book.pdf",
            "source": "kindle",
        })
        assert res.status_code == 200
        assert os.path.exists(os.path.join(thumb_dir, "book.jpg"))

    def test_regenerate_from_webp_when_pdf_missing(self, client, tmp_data_dir, make_webp):
        """PDF 不在時は images/ 先頭 WebP から PIL 経路でサムネイル JPG を生成する（image-only モード）。"""
        from PIL import Image

        img_dir = tmp_data_dir["IMAGES_DIR"]
        thumb_dir = tmp_data_dir["THUMBNAIL_DIR"]
        make_webp(os.path.join(img_dir, "book", "1.webp"), color=(255, 0, 0), size=(400, 600))

        res = client.post("/api/thumbnails/regenerate", json={
            "path": "",
            "name": "book.pdf",
            "source": "generated",
        })
        assert res.status_code == 200
        thumb_path = os.path.join(thumb_dir, "book.jpg")
        assert os.path.exists(thumb_path)
        # 生成された JPEG が PIL で読める
        with Image.open(thumb_path) as img:
            assert img.format == "JPEG"

    def test_regenerate_404_when_no_source(self, client, tmp_data_dir):
        res = client.post("/api/thumbnails/regenerate", json={
            "path": "",
            "name": "nope.pdf",
            "source": "kindle",
        })
        assert res.status_code == 404

    def test_regenerate_400_with_traversal(self, client, tmp_data_dir):
        res = client.post("/api/thumbnails/regenerate", json={
            "path": "../etc",
            "name": "book.pdf",
            "source": "kindle",
        })
        assert res.status_code == 400

    def test_regenerate_invalid_source_returns_400(self, client, tmp_data_dir):
        res = client.post("/api/thumbnails/regenerate", json={
            "path": "",
            "name": "book.pdf",
            "source": "invalid",
        })
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/thumbnails/regenerate_bulk
# ---------------------------------------------------------------------------

class TestRegenerateThumbnailBulk:
    def test_partial_success_and_failure(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "ok.pdf"))

        res = client.post("/api/thumbnails/regenerate_bulk", json={
            "names": ["ok.pdf", "missing.pdf"],
            "path": "",
            "source": "kindle",
        })
        assert res.status_code == 200
        body = res.json()
        assert body["succeeded"] == ["ok.pdf"]
        assert body["failed"] == ["missing.pdf"]

    def test_all_success(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "a.pdf"))
        make_pdf(os.path.join(pdf_dir, "b.pdf"))

        res = client.post("/api/thumbnails/regenerate_bulk", json={
            "names": ["a.pdf", "b.pdf"],
            "path": "",
            "source": "kindle",
        })
        body = res.json()
        assert sorted(body["succeeded"]) == ["a.pdf", "b.pdf"]
        assert body["failed"] == []

    def test_continues_after_failure(self, client, tmp_data_dir, make_pdf):
        """途中で失敗しても全件処理が続行される。"""
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "first.pdf"))
        make_pdf(os.path.join(pdf_dir, "third.pdf"))

        res = client.post("/api/thumbnails/regenerate_bulk", json={
            "names": ["first.pdf", "second.pdf", "third.pdf"],
            "path": "",
            "source": "kindle",
        })
        body = res.json()
        # 第2項目で失敗しても third まで処理される
        assert "first.pdf" in body["succeeded"]
        assert "third.pdf" in body["succeeded"]
        assert body["failed"] == ["second.pdf"]

    def test_400_with_traversal(self, client, tmp_data_dir):
        res = client.post("/api/thumbnails/regenerate_bulk", json={
            "names": ["../etc.pdf"],
            "path": "",
            "source": "kindle",
        })
        assert res.status_code == 400

    def test_invalid_source_returns_400(self, client, tmp_data_dir):
        res = client.post("/api/thumbnails/regenerate_bulk", json={
            "names": ["a.pdf"],
            "path": "",
            "source": "invalid",
        })
        assert res.status_code == 400
