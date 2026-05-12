"""
config モジュールのユニットテスト。

ソース別ディレクトリ解決ヘルパーの挙動を確認する。

実行方法:
    cd backend
    uv run pytest tests/test_config.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import VALID_SOURCES, get_dirs_by_source


class TestGetDirsBySource:
    def test_generated_default(self):
        dirs = get_dirs_by_source("doujin")
        assert "pdf" in dirs
        assert "thumb" in dirs
        assert "img" in dirs
        assert "thumb_url_prefix" in dirs
        assert dirs["thumb_url_prefix"] == "/thumbnails"

    def test_comic(self):
        dirs = get_dirs_by_source("comic")
        assert dirs["thumb_url_prefix"] == "/comic/thumbnails"
        # comic ディレクトリを指している
        assert "comic" in dirs["pdf"].lower()

    def test_novel(self):
        dirs = get_dirs_by_source("novel")
        assert dirs["thumb_url_prefix"] == "/kindle_novel/thumbnails"
        assert "kindle_novel" in dirs["pdf"].lower()

    def test_unknown_source_falls_back_to_generated(self):
        """`generated` 以外で kindle/novel に該当しない値はデフォルト（generated）を返す。"""
        dirs = get_dirs_by_source("foo")
        assert dirs["thumb_url_prefix"] == "/thumbnails"

    def test_all_valid_sources_return_dict(self):
        for src in VALID_SOURCES:
            dirs = get_dirs_by_source(src)
            assert isinstance(dirs, dict)
            assert "pdf" in dirs


class TestValidSources:
    def test_contains_three_sources(self):
        assert set(VALID_SOURCES) == {"doujin", "comic", "novel"}
