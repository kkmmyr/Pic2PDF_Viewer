"""
routers.library のユニットテスト。

書籍一覧（/api/pdfs）・書籍画像一覧（/api/books/{path}/images）・
リネーム（PATCH /api/rename）・削除（DELETE /api/pdfs）を検証する。

実行方法:
    cd backend
    uv run pytest tests/test_router_library.py -v
"""
import os

from services.meta_store import load_meta, save_meta


# ---------------------------------------------------------------------------
# GET /api/pdfs (generated: images/ 走査)
# ---------------------------------------------------------------------------

class TestListPdfsGenerated:
    def test_lists_books_with_webps(self, client, tmp_data_dir, make_webp):
        img_dir = tmp_data_dir["IMAGES_DIR"]
        make_webp(os.path.join(img_dir, "alpha", "1.webp"))
        make_webp(os.path.join(img_dir, "beta", "1.webp"))

        res = client.get("/api/pdfs?source=doujin")
        assert res.status_code == 200
        data = res.json()
        names = {f["name"] for f in data["files"]}
        assert names == {"alpha.pdf", "beta.pdf"}

    def test_excludes_empty_directories(self, client, tmp_data_dir, make_webp):
        img_dir = tmp_data_dir["IMAGES_DIR"]
        make_webp(os.path.join(img_dir, "has_image", "1.webp"))
        os.makedirs(os.path.join(img_dir, "empty_dir"))

        res = client.get("/api/pdfs?source=doujin")
        names = {f["name"] for f in res.json()["files"]}
        assert names == {"has_image.pdf"}

    def test_thumbnail_url_when_thumb_exists(self, client, tmp_data_dir, make_webp):
        img_dir = tmp_data_dir["IMAGES_DIR"]
        thumb_dir = tmp_data_dir["THUMBNAIL_DIR"]
        make_webp(os.path.join(img_dir, "book", "1.webp"))
        thumb_path = os.path.join(thumb_dir, "book.jpg")
        os.makedirs(thumb_dir, exist_ok=True)
        with open(thumb_path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0")  # JPEG magic

        res = client.get("/api/pdfs?source=doujin")
        files = res.json()["files"]
        book = next(f for f in files if f["name"] == "book.pdf")
        assert book["thumbnail"] == "/thumbnails/book.jpg"

    def test_thumbnail_null_when_thumb_missing(self, client, tmp_data_dir, make_webp):
        """サムネイル不在時は null（バックグラウンドで生成される）。"""
        img_dir = tmp_data_dir["IMAGES_DIR"]
        make_webp(os.path.join(img_dir, "newbook", "1.webp"))

        res = client.get("/api/pdfs?source=doujin")
        files = res.json()["files"]
        book = next(f for f in files if f["name"] == "newbook.pdf")
        assert book["thumbnail"] is None

    def test_background_task_creates_thumbnail_from_webp(self, client, tmp_data_dir, make_webp):
        """サムネイル不在時の BackgroundTasks が WebP から JPG を実際に生成する（image-only モード）。

        fitz は WebP を読めないため、PIL ベースの pdf_generator.generate_thumbnail
        を使う必要がある（バックエンド編 §7.3 / 計画書 §8.1 参照）。
        """
        from PIL import Image

        img_dir = tmp_data_dir["IMAGES_DIR"]
        thumb_dir = tmp_data_dir["THUMBNAIL_DIR"]
        make_webp(os.path.join(img_dir, "fresh", "1.webp"), size=(400, 600))

        # /api/pdfs を叩くと BackgroundTasks が起動する。TestClient は同期実行する。
        res = client.get("/api/pdfs?source=doujin")
        assert res.status_code == 200

        # BackgroundTasks 完了後、サムネイル JPG が生成されている
        thumb_path = os.path.join(thumb_dir, "fresh.jpg")
        assert os.path.exists(thumb_path)
        with Image.open(thumb_path) as img:
            assert img.format == "JPEG"

    def test_returns_empty_when_path_not_exist(self, client, tmp_data_dir):
        res = client.get("/api/pdfs?path=nope&source=doujin")
        assert res.status_code == 200
        assert res.json() == {"files": [], "current_path": "nope"}

    def test_path_traversal_rejected(self, client, tmp_data_dir):
        res = client.get("/api/pdfs?path=../etc&source=doujin")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/pdfs (kindle: PDF ファイル走査)
# ---------------------------------------------------------------------------

class TestListPdfsKindle:
    def test_lists_pdf_files(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "book1.pdf"))
        make_pdf(os.path.join(pdf_dir, "book2.pdf"))

        res = client.get("/api/pdfs?source=comic")
        assert res.status_code == 200
        names = {f["name"] for f in res.json()["files"]}
        assert names == {"book1.pdf", "book2.pdf"}

    def test_excludes_non_pdf(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "book.pdf"))
        with open(os.path.join(pdf_dir, "readme.txt"), "w") as f:
            f.write("hi")

        res = client.get("/api/pdfs?source=comic")
        names = {f["name"] for f in res.json()["files"]}
        assert names == {"book.pdf"}

    def test_subdirectory_path(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "series_a", "vol1.pdf"))

        res = client.get("/api/pdfs?path=series_a&source=comic")
        names = {f["name"] for f in res.json()["files"]}
        assert names == {"vol1.pdf"}

    def test_invalid_source_returns_400(self, client, tmp_data_dir):
        """generated/kindle/novel 以外は 400 で弾かれる（Depends(validated_source) 経由）。"""
        res = client.get("/api/pdfs?source=invalid")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/books/{path}/images
# ---------------------------------------------------------------------------

class TestListBookImages:
    def test_returns_natsorted_image_urls(self, client, tmp_data_dir, make_webp):
        img_dir = tmp_data_dir["IMAGES_DIR"]
        for n in ["1.webp", "2.webp", "10.webp"]:
            make_webp(os.path.join(img_dir, "book", n))

        res = client.get("/api/books/book/images?source=doujin")
        assert res.status_code == 200
        urls = res.json()["images"]
        # natsort: 1, 2, 10 の順
        assert urls[0].endswith("/1.webp")
        assert urls[1].endswith("/2.webp")
        assert urls[2].endswith("/10.webp")

    def test_404_when_path_missing(self, client, tmp_data_dir):
        res = client.get("/api/books/nope/images?source=doujin")
        assert res.status_code == 404

    def test_400_when_path_is_file(self, client, tmp_data_dir):
        img_dir = tmp_data_dir["IMAGES_DIR"]
        os.makedirs(img_dir, exist_ok=True)
        with open(os.path.join(img_dir, "afile"), "w") as f:
            f.write("x")
        res = client.get("/api/books/afile/images?source=doujin")
        assert res.status_code == 400

    def test_invalid_source_returns_400(self, client, tmp_data_dir):
        res = client.get("/api/books/anything/images?source=invalid")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /api/rename
# ---------------------------------------------------------------------------

class TestRename:
    def test_rename_pdf_updates_three_assets(self, client, tmp_data_dir, make_pdf, make_webp):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        thumb_dir = tmp_data_dir["KINDLE_THUMBNAIL_DIR"]
        img_dir = tmp_data_dir["KINDLE_IMAGES_DIR"]

        make_pdf(os.path.join(pdf_dir, "old.pdf"))
        os.makedirs(thumb_dir, exist_ok=True)
        with open(os.path.join(thumb_dir, "old.jpg"), "wb") as f:
            f.write(b"x")
        make_webp(os.path.join(img_dir, "old", "1.webp"))

        res = client.patch("/api/rename", json={
            "path": "",
            "old_name": "old.pdf",
            "new_name": "new.pdf",
            "is_folder": False,
            "source": "comic",
        })
        assert res.status_code == 200

        assert os.path.exists(os.path.join(pdf_dir, "new.pdf"))
        assert os.path.exists(os.path.join(thumb_dir, "new.jpg"))
        assert os.path.exists(os.path.join(img_dir, "new"))
        assert not os.path.exists(os.path.join(pdf_dir, "old.pdf"))

    def test_rename_carries_meta_to_new_key(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "old.pdf"))

        save_meta("comic", {"old.pdf": {"authors": ["A"], "genre": "テスト"}})

        res = client.patch("/api/rename", json={
            "path": "",
            "old_name": "old.pdf",
            "new_name": "new.pdf",
            "is_folder": False,
            "source": "comic",
        })
        assert res.status_code == 200

        meta = load_meta("comic")
        assert "old.pdf" not in meta
        assert meta["new.pdf"]["authors"] == ["A"]
        assert meta["new.pdf"]["genre"] == "テスト"

    def test_rename_folder_updates_meta_prefix(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        os.makedirs(os.path.join(pdf_dir, "old_folder"))
        make_pdf(os.path.join(pdf_dir, "old_folder", "a.pdf"))

        save_meta("comic", {"old_folder/a.pdf": {"authors": ["X"]}})

        res = client.patch("/api/rename", json={
            "path": "",
            "old_name": "old_folder",
            "new_name": "new_folder",
            "is_folder": True,
            "source": "comic",
        })
        assert res.status_code == 200

        meta = load_meta("comic")
        assert "old_folder/a.pdf" not in meta
        assert meta["new_folder/a.pdf"]["authors"] == ["X"]

    def test_rename_404_when_missing(self, client, tmp_data_dir):
        res = client.patch("/api/rename", json={
            "path": "",
            "old_name": "nope.pdf",
            "new_name": "new.pdf",
            "is_folder": False,
            "source": "comic",
        })
        assert res.status_code == 404

    def test_rename_400_when_dst_exists(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "old.pdf"))
        make_pdf(os.path.join(pdf_dir, "exists.pdf"))

        res = client.patch("/api/rename", json={
            "path": "",
            "old_name": "old.pdf",
            "new_name": "exists.pdf",
            "is_folder": False,
            "source": "comic",
        })
        assert res.status_code == 400

    def test_rename_400_with_traversal(self, client, tmp_data_dir):
        res = client.patch("/api/rename", json={
            "path": "",
            "old_name": "../etc",
            "new_name": "new.pdf",
            "is_folder": False,
            "source": "comic",
        })
        assert res.status_code == 400

    def test_rename_invalid_source_returns_400(self, client, tmp_data_dir):
        res = client.patch("/api/rename", json={
            "path": "",
            "old_name": "old.pdf",
            "new_name": "new.pdf",
            "is_folder": False,
            "source": "invalid",
        })
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /api/pdfs
# ---------------------------------------------------------------------------

class TestDeletePdfs:
    def test_delete_multiple_files(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        for n in ["a.pdf", "b.pdf", "c.pdf"]:
            make_pdf(os.path.join(pdf_dir, n))

        res = client.request(
            "DELETE",
            "/api/pdfs",
            json={"names": ["a.pdf", "b.pdf"], "path": "", "source": "comic"},
        )
        assert res.status_code == 200
        assert res.json()["deleted_count"] == 2
        assert not os.path.exists(os.path.join(pdf_dir, "a.pdf"))
        assert not os.path.exists(os.path.join(pdf_dir, "b.pdf"))
        assert os.path.exists(os.path.join(pdf_dir, "c.pdf"))

    def test_delete_removes_meta_entry(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "doomed.pdf"))

        save_meta("comic", {
            "doomed.pdf": {"authors": ["X"]},
            "alive.pdf": {"authors": ["Y"]},
        })

        client.request(
            "DELETE",
            "/api/pdfs",
            json={"names": ["doomed.pdf"], "path": "", "source": "comic"},
        )

        meta = load_meta("comic")
        assert "doomed.pdf" not in meta
        assert "alive.pdf" in meta

    def test_partial_failure_returns_errors_with_partial_success(self, client, tmp_data_dir, make_pdf):
        pdf_dir = tmp_data_dir["KINDLE_PDF_DIR"]
        make_pdf(os.path.join(pdf_dir, "exists.pdf"))

        res = client.request(
            "DELETE",
            "/api/pdfs",
            json={"names": ["exists.pdf", "missing.pdf"], "path": "", "source": "comic"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["deleted_count"] == 1
        assert any("missing.pdf" in e for e in body["errors"])

    def test_all_failure_returns_500(self, client, tmp_data_dir):
        res = client.request(
            "DELETE",
            "/api/pdfs",
            json={"names": ["nope1.pdf", "nope2.pdf"], "path": "", "source": "comic"},
        )
        assert res.status_code == 500

    def test_400_with_traversal(self, client, tmp_data_dir):
        res = client.request(
            "DELETE",
            "/api/pdfs",
            json={"names": ["../etc.pdf"], "path": "", "source": "comic"},
        )
        assert res.status_code == 400

    def test_invalid_source_returns_400(self, client, tmp_data_dir):
        res = client.request(
            "DELETE",
            "/api/pdfs",
            json={"names": ["x.pdf"], "path": "", "source": "invalid"},
        )
        assert res.status_code == 400
