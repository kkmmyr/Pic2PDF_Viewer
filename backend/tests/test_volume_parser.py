"""volume_parser の境界ケーステスト。

`series_resolver` から切り出した純粋関数のため、テストは I/O なしで完結する。
パターン追加・修正時のリグレッション防止が主目的。
"""

import pytest

from services.volume_parser import parse_pair_volume_indexes, parse_volume_index


class TestParseVolumeIndex:
    @pytest.mark.parametrize(
        "suffix,expected",
        [
            # 整数
            ("1", 1.0),
            ("3", 3.0),
            ("10", 10.0),
            ("第3巻", 3.0),
            ("3巻", 3.0),
            ("第3", 3.0),
            ("03", 3.0),
            # 前後空白許容
            ("  3  ", 3.0),
        ],
    )
    def test_integer_volumes(self, suffix, expected):
        assert parse_volume_index(suffix) == expected

    @pytest.mark.parametrize(
        "suffix,expected",
        [
            ("2.5", 2.5),
            ("4.5", 4.5),
            ("0.5", 0.5),
        ],
    )
    def test_decimal_volumes(self, suffix, expected):
        assert parse_volume_index(suffix) == expected

    @pytest.mark.parametrize(
        "suffix,expected",
        [
            ("vol.5", 5.0),
            ("Vol.5", 5.0),
            ("VOL.5", 5.0),
            ("vol5", 5.0),  # ドットなしも許容
            ("vol.2.5", 2.5),
            ("VOL.2.5", 2.5),
        ],
    )
    def test_vol_notation(self, suffix, expected):
        assert parse_volume_index(suffix) == expected

    @pytest.mark.parametrize(
        "suffix,expected",
        [
            ("(上)", 1.0),
            ("(中)", 2.0),
            ("(下)", 3.0),
            ("(前)", 1.0),
            ("(後)", 2.0),
            ("（上）", 1.0),  # 全角括弧
            ("（下）", 3.0),
        ],
    )
    def test_paren_notation(self, suffix, expected):
        assert parse_volume_index(suffix) == expected

    def test_paren_multi_char_returns_none(self):
        # 「上下」など複数文字並びは曖昧なので非対応
        assert parse_volume_index("(上下)") is None

    @pytest.mark.parametrize(
        "suffix,expected",
        [
            ("一", 1.0),
            ("三", 3.0),
            ("十", 10.0),
            ("第三", 3.0),
            ("第三巻", 3.0),
            ("三巻", 3.0),
        ],
    )
    def test_kanji_single_char(self, suffix, expected):
        assert parse_volume_index(suffix) == expected

    def test_kanji_two_chars_unsupported(self):
        # 「十一」「十二」… は曖昧さ回避のため非対応
        assert parse_volume_index("十一") is None
        assert parse_volume_index("第十二巻") is None

    @pytest.mark.parametrize(
        "suffix",
        [
            "",
            "   ",
            "abc",
            "外伝",
            "番外編",
            "1.2.3",  # 不正なフォーマット
        ],
    )
    def test_no_match_returns_none(self, suffix):
        assert parse_volume_index(suffix) is None


class TestParsePairVolumeIndexes:
    def test_both_match_normally(self):
        # 通常ケース: 両方マッチ
        assert parse_pair_volume_indexes("1", "2") == (1.0, 2.0)
        assert parse_pair_volume_indexes("第3巻", "第4巻") == (3.0, 4.0)

    def test_blank_paired_with_int_ge_2_treats_blank_as_1(self):
        # 「巻数なし＝1巻」ルール: 空 + 2以上整数 → 空側を 1 巻として扱う
        assert parse_pair_volume_indexes("", "2") == (1.0, 2.0)
        assert parse_pair_volume_indexes("", "3") == (1.0, 3.0)
        assert parse_pair_volume_indexes("3", "") == (3.0, 1.0)

    def test_blank_paired_with_1_does_not_apply_rule(self):
        # 1 巻 + 空 では「両方 1 巻」になるリスクがあるため適用しない
        a, b = parse_pair_volume_indexes("", "1")
        assert a is None
        assert b == 1.0

    def test_blank_paired_with_decimal_does_not_apply_rule(self):
        # 小数巻には「巻数なし＝1巻」ルールを適用しない（曖昧さ回避）
        a, b = parse_pair_volume_indexes("", "2.5")
        assert a is None
        assert b == 2.5

    def test_both_blank(self):
        assert parse_pair_volume_indexes("", "") == (None, None)

    def test_both_no_match(self):
        # どちらもマッチしないなら両方 None
        assert parse_pair_volume_indexes("外伝", "番外編") == (None, None)
