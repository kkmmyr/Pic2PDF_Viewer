"""HTTP characterization of image listing before moving filesystem work."""

import os
from pathlib import Path
from urllib.parse import quote

import pytest

SOURCES = [
    ("doujin", "IMAGES_DIR", "/images"),
    ("comic", "COMIC_IMAGES_DIR", "/comic/images"),
    ("novel", "KINDLE_NOVEL_IMAGES_DIR", "/kindle_novel/images"),
]


@pytest.mark.parametrize(("source", "directory", "prefix"), SOURCES)
def test_nested_images_preserve_order_encoding_version_and_source(client, tmp_data_dir, source, directory, prefix):
    book = "series/書籍 #1"
    target = Path(tmp_data_dir[directory]) / book
    target.mkdir(parents=True)
    for name in ("10.PNG", "2.webp", "1.jpg", "notes.txt"):
        (target / name).write_bytes(b"listing-only fixture")
    expected = [
        f"{prefix}/{quote(book, safe='/')}/{name}?v={(target / name).stat().st_mtime_ns}"
        for name in ("1.jpg", "2.webp", "10.PNG")
    ]

    response = client.get(f"/api/books/{quote(book, safe='/')}/images", params={"source": source})

    assert response.status_code == 200
    assert response.json() == {"images": expected}
    assert {entry.name for entry in target.iterdir()} == {"10.PNG", "2.webp", "1.jpg", "notes.txt"}


@pytest.mark.parametrize(("source", "directory", "prefix"), SOURCES)
def test_empty_image_directory_returns_empty_list(client, tmp_data_dir, source, directory, prefix):
    (Path(tmp_data_dir[directory]) / "empty").mkdir()
    response = client.get("/api/books/empty/images", params={"source": source})
    assert response.status_code == 200
    assert response.json() == {"images": []}


@pytest.mark.parametrize("path", ["..%5Coutside", "C%3A%5Coutside", "%5C%5Cserver%5Cshare"])
def test_image_listing_rejects_unsafe_path(client, path):
    response = client.get(f"/api/books/{path}/images")
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid path"}


@pytest.mark.parametrize(
    ("path", "status", "detail"), [("missing", 404, "Images not found"), ("file", 400, "Not a directory")]
)
def test_image_directory_errors_preserve_http_details(client, tmp_data_dir, path, status, detail):
    (Path(tmp_data_dir["IMAGES_DIR"]) / "file").write_text("file", encoding="utf-8")
    response = client.get(f"/api/books/{path}/images")
    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_image_disappearing_after_listing_is_not_a_missing_directory(client, tmp_data_dir, monkeypatch):
    target = Path(tmp_data_dir["IMAGES_DIR"]) / "book"
    target.mkdir()
    image = target / "1.png"
    image.write_bytes(b"listing-only fixture")
    real_stat = os.stat

    def disappeared(path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)) and Path(path) == image:
            raise FileNotFoundError("image disappeared")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", disappeared)
    response = client.get("/api/books/book/images")
    assert response.status_code == 500
    assert response.json() == {"detail": "image disappeared"}
