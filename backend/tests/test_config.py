"""
config モジュールのユニットテスト。

ソース別ディレクトリ解決ヘルパーの挙動を確認する。

実行方法:
    cd backend
    uv run pytest tests/test_config.py -v
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import VALID_SOURCES, get_dirs_by_source
from config.novel_db import _NovelDbSettings


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


class TestNovelDbSettings:
    def test_lance_path_defaults_to_novel_db_sibling(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        novel_db_dir = tmp_path / "stable-data" / "novel_db"
        monkeypatch.setenv("NOVEL_DB_DIR", str(novel_db_dir))
        monkeypatch.delenv("NOVEL_DB_LANCE_PATH", raising=False)

        settings = _NovelDbSettings()

        assert settings.NOVEL_DB_LANCE_PATH == str(novel_db_dir.parent / "novel.lancedb")

    def test_explicit_lance_path_overrides_derived_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        explicit = tmp_path / "explicit" / "index.lancedb"
        monkeypatch.setenv("NOVEL_DB_DIR", str(tmp_path / "novel_db"))
        monkeypatch.setenv("NOVEL_DB_LANCE_PATH", str(explicit))

        settings = _NovelDbSettings()

        assert settings.NOVEL_DB_LANCE_PATH == str(explicit)
