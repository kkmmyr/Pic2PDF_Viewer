"""
routers.pdfs のユニットテスト。

ページ削除（POST /api/pdfs/{filename}/delete_pages）と
PDF 結合（POST /api/pdfs/merge）を検証する。

実行方法:
    cd backend
    uv run pytest tests/test_router_pdfs.py -v
"""
import sys
import os

import pytest
import fitz

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# POST /api/pdfs/{filename}/delete_pages
# ---------------------------------------------------------------------------

class TestDeletePages:
    def test_delete_single_page(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "book.pdf"), page_count=5)

        res = client.post(
            "/api/pdfs/book.pdf/delete_pages?source=kindle",
            json={"page_indices": [0]},
        )
        assert res.status_code == 200
        assert res.json()["total_pages"] == 4

    def test_delete_multiple_pages(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "book.pdf"), page_count=10)

        res = client.post(
            "/api/pdfs/book.pdf/delete_pages?source=kindle",
            json={"page_indices": [0, 2, 5]},
        )
        assert res.status_code == 200
        assert res.json()["total_pages"] == 7

    def test_delete_404_when_missing(self, client, tmp_data_dir):
        res = client.post(
            "/api/pdfs/nope.pdf/delete_pages?source=kindle",
            json={"page_indices": [0]},
        )
        assert res.status_code == 404

    def test_delete_500_for_out_of_range(self, client, tmp_data_dir, make_pdf):
        """範囲外インデックスは PdfService が ValueError → log_and_raise_500 で 500。"""
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "book.pdf"), page_count=3)

        res = client.post(
            "/api/pdfs/book.pdf/delete_pages?source=kindle",
            json={"page_indices": [99]},
        )
        assert res.status_code == 500

    def test_thumbnail_regenerated_after_delete(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        thumb_dir = tmp_data_dir["KINDLE_THUMBNAIL_DIR"]
        make_pdf(os.path.join(pdf_dir, "book.pdf"), page_count=5)
        # 古いサムネイルを置く
        os.makedirs(thumb_dir, exist_ok=True)
        old_thumb = os.path.join(thumb_dir, "book.jpg")
        with open(old_thumb, "wb") as f:
            f.write(b"old")

        res = client.post(
            "/api/pdfs/book.pdf/delete_pages?source=kindle",
            json={"page_indices": [0]},
        )
        assert res.status_code == 200

        assert os.path.exists(old_thumb)
        # 上書きされている（"old" よりサイズが大きいはず）
        assert os.path.getsize(old_thumb) > 3

    def test_path_traversal_rejected(self, client, tmp_data_dir):
        res = client.post(
            "/api/pdfs/x.pdf/delete_pages?path=../etc&source=kindle",
            json={"page_indices": [0]},
        )
        assert res.status_code == 400

    def test_invalid_source_returns_400(self, client, tmp_data_dir):
        res = client.post(
            "/api/pdfs/x.pdf/delete_pages?source=invalid",
            json={"page_indices": [0]},
        )
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/pdfs/merge
# ---------------------------------------------------------------------------

class TestMergePdfs:
    def test_merge_two_pdfs(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "a.pdf"), page_count=3)
        make_pdf(os.path.join(pdf_dir, "b.pdf"), page_count=2)

        res = client.post("/api/pdfs/merge", json={
            "names": ["a.pdf", "b.pdf"],
            "output_name": "merged.pdf",
            "path": "",
            "source": "kindle",
        })
        assert res.status_code == 200
        body = res.json()
        assert body["total_pages"] == 5
        assert body["output_name"] == "merged.pdf"

        merged_path = os.path.join(pdf_dir, "merged.pdf")
        assert os.path.exists(merged_path)
        with fitz.open(merged_path) as doc:
            assert len(doc) == 5

    def test_merge_creates_thumbnail(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        thumb_dir = tmp_data_dir["KINDLE_THUMBNAIL_DIR"]
        make_pdf(os.path.join(pdf_dir, "a.pdf"))
        make_pdf(os.path.join(pdf_dir, "b.pdf"))

        client.post("/api/pdfs/merge", json={
            "names": ["a.pdf", "b.pdf"],
            "output_name": "merged.pdf",
            "path": "",
            "source": "kindle",
        })
        assert os.path.exists(os.path.join(thumb_dir, "merged.jpg"))

    def test_merge_400_when_output_exists(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "a.pdf"))
        make_pdf(os.path.join(pdf_dir, "b.pdf"))
        make_pdf(os.path.join(pdf_dir, "merged.pdf"))

        res = client.post("/api/pdfs/merge", json={
            "names": ["a.pdf", "b.pdf"],
            "output_name": "merged.pdf",
            "path": "",
            "source": "kindle",
        })
        assert res.status_code == 400

    def test_merge_400_when_too_few_files(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "a.pdf"))

        res = client.post("/api/pdfs/merge", json={
            "names": ["a.pdf"],
            "output_name": "merged.pdf",
            "path": "",
            "source": "kindle",
        })
        assert res.status_code == 400

    def test_merge_400_when_output_not_pdf(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "a.pdf"))
        make_pdf(os.path.join(pdf_dir, "b.pdf"))

        res = client.post("/api/pdfs/merge", json={
            "names": ["a.pdf", "b.pdf"],
            "output_name": "merged.txt",
            "path": "",
            "source": "kindle",
        })
        assert res.status_code == 400

    def test_merge_404_when_input_missing(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "a.pdf"))

        res = client.post("/api/pdfs/merge", json={
            "names": ["a.pdf", "missing.pdf"],
            "output_name": "merged.pdf",
            "path": "",
            "source": "kindle",
        })
        assert res.status_code == 404

    def test_merge_400_with_traversal(self, client, tmp_data_dir):
        res = client.post("/api/pdfs/merge", json={
            "names": ["../etc.pdf", "b.pdf"],
            "output_name": "merged.pdf",
            "path": "",
            "source": "kindle",
        })
        assert res.status_code == 400

    def test_merge_invalid_source_returns_400(self, client, tmp_data_dir):
        res = client.post("/api/pdfs/merge", json={
            "names": ["a.pdf", "b.pdf"],
            "output_name": "merged.pdf",
            "path": "",
            "source": "invalid",
        })
        assert res.status_code == 400
