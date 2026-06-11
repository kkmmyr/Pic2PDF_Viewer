"""services/amazon_csv_parser.py のユニットテスト。"""

from services.amazon_csv_parser import (
    ParsedRow,
    _decode,
    _extract_publisher,
    _extract_volume,
    _parse_authors,
    match_books,
    parse_csv,
)

# ---------------------------------------------------------------------------
# _extract_publisher
# ---------------------------------------------------------------------------

class TestExtractPublisher:
    def test_末尾の括弧をパブリッシャーとして分離する(self):
        title, pub = _extract_publisher("魔法少女まどか☆マギカ (マジカルバナナ)")
        assert pub == "マジカルバナナ"
        assert title == "魔法少女まどか☆マギカ"

    def test_括弧なしはタイトルそのまま(self):
        title, pub = _extract_publisher("ワンピース")
        assert pub == ""
        assert title == "ワンピース"

    def test_複数括弧は末尾のみ分離する(self):
        title, pub = _extract_publisher("タイトル (中の括弧) (レーベル)")
        assert pub == "レーベル"
        assert "中の括弧" in title


# ---------------------------------------------------------------------------
# _extract_volume
# ---------------------------------------------------------------------------

class TestExtractVolume:
    def test_末尾の半角数字を巻番号として抽出する(self):
        title, vol = _extract_volume("おこぼれ姫と円卓の騎士 1")
        assert vol == 1
        assert title == "おこぼれ姫と円卓の騎士"

    def test_第N巻パターンを抽出する(self):
        title, vol = _extract_volume("進撃の巨人 第3巻")
        assert vol == 3

    def test_巻番号なしはNoneを返す(self):
        title, vol = _extract_volume("鬼滅の刃")
        assert vol is None
        assert title == "鬼滅の刃"

    def test_2桁の巻番号(self):
        _, vol = _extract_volume("ワンピース 15")
        assert vol == 15


# ---------------------------------------------------------------------------
# _parse_authors
# ---------------------------------------------------------------------------

class TestParseAuthors:
    def test_Kindle版プレフィックスを除去して著者リストを返す(self):
        fuzetsu = "[Kindle 版] 石田 リンネ, 起家 一子  販売: Amazon Services International, Inc."
        authors = _parse_authors(fuzetsu)
        assert authors == ["石田 リンネ", "起家 一子"]

    def test_単一著者(self):
        authors = _parse_authors("吾峠呼世晴")
        assert authors == ["吾峠呼世晴"]

    def test_空文字列は空リストを返す(self):
        assert _parse_authors("") == []

    def test_読点区切りも対応(self):
        authors = _parse_authors("作者A、作者B")
        assert "作者A" in authors
        assert "作者B" in authors


# ---------------------------------------------------------------------------
# _decode
# ---------------------------------------------------------------------------

class TestDecode:
    def test_UTF8_BOMを正常にデコードする(self):
        text = "商品名,価格\n書籍A,500"
        data = text.encode("utf-8-sig")
        result = _decode(data)
        assert "商品名" in result

    def test_ShiftJISをデコードする(self):
        text = "商品名,価格"
        data = text.encode("shift_jis")
        result = _decode(data)
        assert "商品名" in result

    def test_通常UTF8もデコードできる(self):
        text = "hello,world"
        result = _decode(text.encode("utf-8"))
        assert result == "hello,world"


# ---------------------------------------------------------------------------
# parse_csv
# ---------------------------------------------------------------------------

def _make_csv_bytes(rows: list[dict], encoding: str = "utf-8-sig") -> bytes:
    import csv
    import io
    fieldnames = ["商品名", "商品URL", "付帯情報"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue().encode(encoding)


class TestParseCsv:
    def test_正常行からParsedRowを返す(self):
        data = _make_csv_bytes([{
            "商品名": "ワンピース 1 (ジャンプコミックスDIGITAL)",
            "商品URL": "https://www.amazon.co.jp/dp/B00AJTFTCG/ref=...",
            "付帯情報": "[Kindle 版] 尾田 栄一郎  販売: Amazon Services",
        }])
        rows = parse_csv(data)
        assert len(rows) == 1
        r = rows[0]
        assert r.volume == 1
        assert r.asin == "B00AJTFTCG"
        assert "尾田 栄一郎" in r.authors

    def test_空のCSVは空リストを返す(self):
        data = _make_csv_bytes([])
        assert parse_csv(data) == []

    def test_商品名が空の行はスキップされる(self):
        data = _make_csv_bytes([
            {"商品名": "", "商品URL": "https://example.com/dp/B001/"},
            {"商品名": "正常タイトル", "商品URL": ""},
        ])
        rows = parse_csv(data)
        assert len(rows) == 1
        assert rows[0].csv_title == "正常タイトル"

    def test_ASINなし行もパースできる(self):
        data = _make_csv_bytes([{"商品名": "タイトル", "商品URL": "https://example.com/"}])
        rows = parse_csv(data)
        assert rows[0].asin == ""

    def test_ShiftJISエンコーディングを読める(self):
        data = _make_csv_bytes([{"商品名": "テスト書籍"}], encoding="shift_jis")
        rows = parse_csv(data)
        assert rows[0].csv_title == "テスト書籍"

    def test_複数行を全てパースする(self):
        data = _make_csv_bytes([
            {"商品名": "本A", "商品URL": ""},
            {"商品名": "本B", "商品URL": ""},
            {"商品名": "本C", "商品URL": ""},
        ])
        assert len(parse_csv(data)) == 3


# ---------------------------------------------------------------------------
# match_books
# ---------------------------------------------------------------------------

class TestMatchBooks:
    def _make_row(self, csv_title: str, series_id: str = "", volume: int | None = None) -> ParsedRow:
        return ParsedRow(
            csv_title=csv_title,
            series_id=series_id or csv_title,
            volume=volume,
            publisher="",
            authors=[],
            asin="",
        )

    def test_完全一致でスコアが高い(self):
        row = self._make_row("ワンピース", "ワンピース")
        results = match_books([row], ["ワンピース.pdf"])
        assert results[0].matched_book == "ワンピース.pdf"
        assert results[0].match_score > 0.7

    def test_スコア閾値未満はmatchedBookがNone(self):
        row = self._make_row("全く関係ないタイトル")
        results = match_books([row], ["ABCDEFGHIJK.pdf"])
        assert results[0].matched_book is None

    def test_空の書籍リストは全てNone(self):
        row = self._make_row("ワンピース")
        results = match_books([row], [])
        assert results[0].matched_book is None

    def test_複数書籍の中から最良マッチを選ぶ(self):
        row = self._make_row("鬼滅の刃")
        book_names = ["鬼滅の刃.pdf", "全く違う本.pdf", "別の漫画.pdf"]
        results = match_books([row], book_names)
        assert results[0].matched_book == "鬼滅の刃.pdf"

    def test_複数ParsedRowを全てマッチングする(self):
        rows = [self._make_row("本A"), self._make_row("本B")]
        results = match_books(rows, ["本A.pdf", "本B.pdf"])
        assert len(results) == 2
