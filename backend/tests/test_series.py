"""
services.series_resolver のユニットテスト。

ルールベースのシリーズ判定（タイトル前方一致 + 巻数パターン）の挙動を確認する。

実行方法:
    cd backend
    uv run pytest tests/test_series.py -v
"""
import sys
import os
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.series_resolver import (
    _parse_volume_index,
    _common_prefix,
    _detect_series_in_group,
    run_resolve,
    get_state,
    reset_state,
)


# ---------------------------------------------------------------------------
# _parse_volume_index — 巻数パターンの数値化
# ---------------------------------------------------------------------------

class TestParseVolumeIndex:
    @pytest.mark.parametrize("suffix,expected", [
        (" 1",       1),
        (" 2",       2),
        (" 03",      3),
        (" 第3巻",   3),
        ("第10巻",   10),
        (" vol.4",   4),
        (" Vol 5",   5),
        (" VOL.06",  6),
        ("(上)",      1),
        ("(中)",      2),
        ("(下)",      3),
        ("(前)",      1),
        ("(後)",      2),
        ("(下)",      3),
        ("第三巻",   3),
        ("七",        7),
    ])
    def test_recognized_patterns(self, suffix, expected):
        assert _parse_volume_index(suffix) == expected

    @pytest.mark.parametrize("suffix", [
        "",
        " ",
        " 外伝",
        " 番外編",
        " ABC",
        "(上下)",  # 並びは未対応
    ])
    def test_unrecognized_patterns(self, suffix):
        assert _parse_volume_index(suffix) is None


# ---------------------------------------------------------------------------
# _common_prefix
# ---------------------------------------------------------------------------

class TestCommonPrefix:
    def test_basic(self):
        assert _common_prefix("鬼滅の刃 1", "鬼滅の刃 2") == "鬼滅の刃 "

    def test_no_overlap(self):
        assert _common_prefix("hello", "world") == ""

    def test_full_overlap(self):
        assert _common_prefix("same", "same") == "same"


# ---------------------------------------------------------------------------
# _detect_series_in_group — グループ内のシリーズ検出
# ---------------------------------------------------------------------------

class TestDetectSeriesInGroup:
    def test_simple_series(self):
        # 「鬼滅の刃 1」「鬼滅の刃 2」「鬼滅の刃 3」 → 全部シリーズ化
        group = [
            ("", "鬼滅の刃 1.pdf", "鬼滅の刃 1"),
            ("", "鬼滅の刃 2.pdf", "鬼滅の刃 2"),
            ("", "鬼滅の刃 3.pdf", "鬼滅の刃 3"),
        ]
        result = _detect_series_in_group(group)
        assert len(result) == 3
        # series_title は trim 済みプレフィックス
        for _key, (title, _idx) in result.items():
            assert title == "鬼滅の刃"
        # 各 index が 1, 2, 3 になっている
        indices = sorted(idx for _, (_, idx) in result.items())
        assert indices == [1, 2, 3]

    def test_short_prefix_excluded(self):
        # 「ab1」「ab2」 → 共通プレフィックス「ab」が短いので除外
        group = [
            ("", "ab1.pdf", "ab1"),
            ("", "ab2.pdf", "ab2"),
        ]
        result = _detect_series_in_group(group)
        assert result == {}

    def test_non_volume_suffix_excluded(self):
        # 「進撃の巨人 1」「進撃の巨人 外伝」 → 後者の残部分が巻数パターンでない → ペアとして判定されない
        group = [
            ("", "進撃の巨人 1.pdf", "進撃の巨人 1"),
            ("", "進撃の巨人 外伝.pdf", "進撃の巨人 外伝"),
        ]
        result = _detect_series_in_group(group)
        assert result == {}

    def test_singleton_excluded(self):
        # 1冊だけならシリーズ化しない
        group = [("", "ぼっち本 1.pdf", "ぼっち本 1")]
        result = _detect_series_in_group(group)
        assert result == {}

    def test_mixed_patterns(self):
        # 「ABCDE 1」「ABCDE 第2巻」「ABCDE vol.3」混合
        group = [
            ("", "ABCDE 1.pdf",      "ABCDE 1"),
            ("", "ABCDE 第2巻.pdf",  "ABCDE 第2巻"),
            ("", "ABCDE vol.3.pdf",  "ABCDE vol.3"),
        ]
        result = _detect_series_in_group(group)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# run_resolve（end-to-end）
# ---------------------------------------------------------------------------

@pytest.fixture
def series_env(tmp_path, monkeypatch):
    """run_resolve を tmp_path 配下で動かす環境を作る。"""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    monkeypatch.setattr("config.PDF_DIR", str(pdf_dir))
    monkeypatch.setattr("services.meta_store.DATA_DIR", str(tmp_path))
    return tmp_path, pdf_dir


def _read_meta(tmp_path, source: str = "generated") -> dict:
    p = tmp_path / "meta" / source / "meta.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _seed_meta(tmp_path, entries: dict, source: str = "generated") -> None:
    meta_dir = tmp_path / "meta" / source
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "meta.json").write_text(json.dumps(entries), encoding="utf-8")


class TestRunResolve:
    def test_groups_books_by_author_and_prefix(self, series_env):
        tmp_path, pdf_dir = series_env

        # 同作者・シリーズと同作者・別シリーズと別作者・シリーズを混在させる
        for name in (
            "鬼滅の刃 1.pdf", "鬼滅の刃 2.pdf",
            "進撃の巨人 1.pdf", "進撃の巨人 2.pdf",
            "別本.pdf",
        ):
            (pdf_dir / name).write_bytes(b"")

        _seed_meta(tmp_path, {
            "鬼滅の刃 1.pdf":   {"authors": ["A"]},
            "鬼滅の刃 2.pdf":   {"authors": ["A"]},
            "進撃の巨人 1.pdf": {"authors": ["B"]},
            "進撃の巨人 2.pdf": {"authors": ["B"]},
            "別本.pdf":         {"authors": ["A"]},  # 単独
        })

        reset_state("generated")
        run_resolve("generated")

        meta = _read_meta(tmp_path)
        # 鬼滅の刃ペアは同じ series_id を持つ
        assert meta["鬼滅の刃 1.pdf"]["series_id"] == meta["鬼滅の刃 2.pdf"]["series_id"]
        assert meta["鬼滅の刃 1.pdf"]["series_title"] == "鬼滅の刃"
        assert meta["鬼滅の刃 1.pdf"]["series_index"] == 1
        assert meta["鬼滅の刃 2.pdf"]["series_index"] == 2
        # 進撃の巨人は別作者なので別 series_id
        assert meta["進撃の巨人 1.pdf"]["series_id"] != meta["鬼滅の刃 1.pdf"]["series_id"]
        # 単独本はシリーズ化されない
        assert "series_id" not in meta["別本.pdf"]

        state = get_state("generated")
        assert state.status == "done"
        assert state.created == 2  # 2 シリーズ作成された

    def test_clears_existing_series_on_rerun(self, series_env):
        tmp_path, pdf_dir = series_env

        (pdf_dir / "Old A 1.pdf").write_bytes(b"")
        # 既存の series_id がある状態で run → 単独本になり series_* が消えるはず
        _seed_meta(tmp_path, {
            "Old A 1.pdf": {
                "authors": ["A"],
                "series_id": "stale123",
                "series_title": "Old",
                "series_index": 1,
            },
        })

        reset_state("generated")
        run_resolve("generated")

        meta = _read_meta(tmp_path)
        assert "series_id" not in meta["Old A 1.pdf"]
        assert "series_title" not in meta["Old A 1.pdf"]
        assert "series_index" not in meta["Old A 1.pdf"]

    def test_skips_books_without_authors(self, series_env):
        tmp_path, pdf_dir = series_env

        (pdf_dir / "Foobar 1.pdf").write_bytes(b"")
        (pdf_dir / "Foobar 2.pdf").write_bytes(b"")
        # authors が空 → 作者グループに含まれずシリーズ化対象外
        _seed_meta(tmp_path, {
            "Foobar 1.pdf": {"authors": []},
            "Foobar 2.pdf": {"authors": []},
        })

        reset_state("generated")
        run_resolve("generated")

        meta = _read_meta(tmp_path)
        assert "series_id" not in meta["Foobar 1.pdf"]
        assert "series_id" not in meta["Foobar 2.pdf"]

    def test_preserves_other_fields(self, series_env):
        tmp_path, pdf_dir = series_env

        (pdf_dir / "Series 1.pdf").write_bytes(b"")
        (pdf_dir / "Series 2.pdf").write_bytes(b"")
        _seed_meta(tmp_path, {
            "Series 1.pdf": {
                "authors": ["A"],
                "tags": ["タグ1"],
                "view_count": 5,
                "last_viewed_at": 1700000000.0,
            },
            "Series 2.pdf": {"authors": ["A"]},
        })

        reset_state("generated")
        run_resolve("generated")

        meta = _read_meta(tmp_path)
        # シリーズ化されつつ他フィールドが残る
        assert meta["Series 1.pdf"]["series_id"] == meta["Series 2.pdf"]["series_id"]
        assert meta["Series 1.pdf"]["tags"] == ["タグ1"]
        assert meta["Series 1.pdf"]["view_count"] == 5
        assert meta["Series 1.pdf"]["last_viewed_at"] == 1700000000.0
