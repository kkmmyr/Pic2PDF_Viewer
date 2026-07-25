"""Pic2PDFViewer 既存画像の手動 ASIN 紐付けテスト。"""

from services.kindle_catalog.connection import with_db
from services.kindle_catalog.links import candidates, link, list_unlinked, unlink
from services.kindle_catalog.migrations import upgrade_head
from services.meta_store import load_meta, update_meta_locked


def test_existing_pic2pdf_image_is_candidate_and_requires_explicit_link(tmp_data_dir, make_png):
    upgrade_head()
    make_png(f"{tmp_data_dir['COMIC_IMAGES_DIR']}/テスト作品 1巻/001.png")
    with with_db() as conn:
        conn.execute(
            """
            INSERT INTO books(
                asin, title, title_normalized, category, book_type
            ) VALUES ('B000TEST01', 'テスト作品 1巻', 'テスト作品', 'unknown', 'comic')
            """
        )

    unlinked = list_unlinked()
    suggested = candidates("comic", "テスト作品 1巻.pdf")

    assert unlinked[0]["book_id"] == "テスト作品 1巻.pdf"
    assert suggested[0]["asin"] == "B000TEST01"
    assert load_meta("comic") == {}

    linked = link("comic", "テスト作品 1巻.pdf", "B000TEST01")

    assert linked["asin"] == "B000TEST01"
    assert load_meta("comic")["テスト作品 1巻.pdf"]["asin"] == "B000TEST01"


def test_unlink_preserves_other_pic2pdf_metadata(tmp_data_dir, make_png):
    upgrade_head()
    make_png(f"{tmp_data_dir['KINDLE_NOVEL_IMAGES_DIR']}/小説A/001.png")
    with with_db() as conn:
        conn.execute(
            "INSERT INTO books(asin,title,title_normalized,category,book_type) "
            "VALUES ('B000NOVEL1','小説A','小説A','unknown','novel')"
        )

    def _seed(data):
        data["小説A.pdf"] = {"authors": ["著者"], "read_state": "reading", "asin": "B000NOVEL1"}

    update_meta_locked("novel", _seed)

    unlink("novel", "小説A.pdf")

    entry = load_meta("novel")["小説A.pdf"]
    assert entry["authors"] == ["著者"]
    assert entry["read_state"] == "reading"
    assert "asin" not in entry
