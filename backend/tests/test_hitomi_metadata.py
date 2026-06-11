"""services.hitomi.metadata.parse_galleryinfo のユニットテスト（純粋関数）。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.hitomi.metadata import HitomiMetadataError, parse_galleryinfo


class TestParseGalleryinfo:
    def test_minimal_input(self):
        text = 'var galleryinfo = {"id":"123","title":"sample"};'
        result = parse_galleryinfo(text)
        assert result["id"] == "123"
        assert result["title"] == "sample"

    def test_no_trailing_semicolon(self):
        text = 'var galleryinfo = {"title": "no-semi"}'
        assert parse_galleryinfo(text)["title"] == "no-semi"

    def test_full_metadata_shape(self):
        text = """var galleryinfo = {
            "id": "2034567",
            "title": "サンプル",
            "artists": [{"artist":"aka shio","url":"/artist/aka_shio.html"}],
            "language": "japanese",
            "type": "manga",
            "date": "2026-04-28 00:00:00-05",
            "files": [{"name":"01.webp"},{"name":"02.webp"},{"name":"03.webp"}]
        };"""
        result = parse_galleryinfo(text)
        assert result["title"] == "サンプル"
        assert len(result["files"]) == 3
        assert result["language"] == "japanese"

    def test_leading_whitespace_ok(self):
        text = '\n   var galleryinfo = {"id":"1"};'
        assert parse_galleryinfo(text)["id"] == "1"

    def test_missing_prefix_raises(self):
        with pytest.raises(HitomiMetadataError, match="prefix not found"):
            parse_galleryinfo('{"id": "1"}')

    def test_invalid_json_raises(self):
        with pytest.raises(HitomiMetadataError, match="JSON parse failed"):
            parse_galleryinfo("var galleryinfo = {not valid json};")
