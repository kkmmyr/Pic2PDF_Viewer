"""services._title_normalizer のユニットテスト。"""

from services._title_normalizer import is_meaningful, normalize_title


class TestIsMeaningful:
    def test_通常の文字列はTrue(self):
        assert is_meaningful("ワンピース") is True

    def test_Noneはfalse(self):
        assert is_meaningful(None) is False

    def test_空文字はFalse(self):
        assert is_meaningful("") is False

    def test_not_applicableはFalse(self):
        assert is_meaningful("not applicable") is False
        assert is_meaningful("NOT APPLICABLE") is False

    def test_空白のみはFalse(self):
        assert is_meaningful("   ") is False


class TestNormalizeTitle:
    def test_巻番号を除去する(self):
        assert normalize_title("ワンピース 1") == "ワンピース"

    def test_全角括弧の巻番号を除去する(self):
        assert normalize_title("ドラゴンボール（1）") == "ドラゴンボール"

    def test_第N巻を除去する(self):
        assert normalize_title("進撃の巨人 第1巻") == "進撃の巨人"

    def test_レーベル括弧を除去する(self):
        assert normalize_title("転生したらスライムだった件（転スラ文庫）") == "転生したらスライムだった件"

    def test_先頭角括弧プレフィックスを除去する(self):
        assert normalize_title("【電子版】魔法少女まどか☆マギカ") == "魔法少女まどか☆マギカ"

    def test_変更不要な文字列はそのまま(self):
        assert normalize_title("ハリー・ポッター") == "ハリー・ポッター"

    def test_空文字は空文字(self):
        assert normalize_title("") == ""
