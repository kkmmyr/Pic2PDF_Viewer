from services.novel_db.series_meta import book_names_for_series, build_book_series_ids


def test_build_book_series_ids_keeps_only_valid_pdf_entries():
    meta = {
        "one.pdf": {"series_id": "series-a"},
        "two.pdf": {"series_id": ""},
        "directory": {"series_id": "series-a"},
        "three.pdf": {"series_id": 123},
    }

    assert build_book_series_ids(meta) == {"one": "series-a"}


def test_book_names_for_series_uses_existing_index_without_reloading():
    index = {"one": "series-a", "two": "series-b", "three": "series-a"}

    assert book_names_for_series("series-a", index) == {"one", "three"}
