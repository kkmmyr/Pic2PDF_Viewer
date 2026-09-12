"""Image metadata can be consumed without HTTP or application startup."""

from pathlib import Path

from services.library.image_listing import BookImageFile, list_book_image_files


def test_list_image_metadata_without_source_configuration(tmp_path: Path) -> None:
    for name in ("10.PNG", "2.webp", "notes.txt"):
        (tmp_path / name).write_bytes(b"metadata fixture")

    assert list_book_image_files(str(tmp_path)) == [
        BookImageFile("2.webp", (tmp_path / "2.webp").stat().st_mtime_ns),
        BookImageFile("10.PNG", (tmp_path / "10.PNG").stat().st_mtime_ns),
    ]
