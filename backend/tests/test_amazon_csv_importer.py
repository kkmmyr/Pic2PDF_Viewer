"""services/amazon_csv_importer.py のユニットテスト。"""
import csv
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from services.amazon_csv_importer import (
    ImportResult,
    _build_lookup,
    _LookupEntry,
    _match,
    _normalize,
    _parse_digital_orders,
    run_import,
)
from services.amazon_csv_parser import ParsedRow

# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_巻番号を除去する(self):
        assert _normalize("ワンピース 1") == "ワンピース"

    def test_第N巻パターンを除去する(self):
        assert _normalize("鬼滅の刃 第3巻") == "鬼滅の刃"

    def test_末尾の括弧レーベルを除去する(self):
        result = _normalize("進撃の巨人（コミックス）")
        assert "コミックス" not in result

    def test_全角スペースを正規化する(self):
        result = _normalize("タイトル　1")
        assert result == "タイトル"

    def test_空文字は空文字を返す(self):
        assert _normalize("") == ""

    def test_先頭の括弧ノイズを除去する(self):
        result = _normalize("【完結】ワンピース")
        assert "完結" not in result
        assert "ワンピース" in result


# ---------------------------------------------------------------------------
# _parse_digital_orders
# ---------------------------------------------------------------------------

def _make_digital_csv(rows: list[dict], encoding: str = "utf-8-sig") -> bytes:
    fields = ["Order ID", "ASIN", "Digital Order Item ID", "Product Name",
              "Subscription Order Type", "Seller of Record"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fields})
    return buf.getvalue().encode(encoding)


class TestParseDigitalOrders:
    def test_存在しないパスは空辞書を返す(self, tmp_path):
        result = _parse_digital_orders(tmp_path / "none.csv")
        assert result == {}

    def test_正常行からLookupEntryを作成する(self, tmp_path):
        data = _make_digital_csv([{
            "Order ID": "D01",
            "ASIN": "B001234567",
            "Digital Order Item ID": "doi1",
            "Product Name": "テスト書籍",
        }])
        csv_path = tmp_path / "orders.csv"
        csv_path.write_bytes(data)
        result = _parse_digital_orders(csv_path)
        assert "B001234567" in result
        assert result["B001234567"].title == "テスト書籍"

    def test_サブスクタイプは除外される(self, tmp_path):
        data = _make_digital_csv([{
            "Order ID": "D02",
            "ASIN": "B999999999",
            "Digital Order Item ID": "doi2",
            "Product Name": "サブスク",
            "Subscription Order Type": "Subscription_Renewal",
        }])
        csv_path = tmp_path / "orders.csv"
        csv_path.write_bytes(data)
        result = _parse_digital_orders(csv_path)
        assert "B999999999" not in result

    def test_同一ASINの重複行は1件に集約される(self, tmp_path):
        data = _make_digital_csv([
            {"Order ID": "D03", "ASIN": "B111111111", "Digital Order Item ID": "doi3a", "Product Name": "本A"},
            {"Order ID": "D03", "ASIN": "B111111111", "Digital Order Item ID": "doi3b", "Product Name": "本A"},
        ])
        csv_path = tmp_path / "orders.csv"
        csv_path.write_bytes(data)
        result = _parse_digital_orders(csv_path)
        assert len([k for k in result if k == "B111111111"]) == 1

    def test_Product_Nameが空の行はスキップされる(self, tmp_path):
        data = _make_digital_csv([{
            "Order ID": "D04",
            "ASIN": "B222222222",
            "Digital Order Item ID": "doi4",
            "Product Name": "",
        }])
        csv_path = tmp_path / "orders.csv"
        csv_path.write_bytes(data)
        result = _parse_digital_orders(csv_path)
        assert "B222222222" not in result


# ---------------------------------------------------------------------------
# _build_lookup
# ---------------------------------------------------------------------------

class TestBuildLookup:
    def _row(self, asin: str, title: str, authors: list[str] | None = None) -> ParsedRow:
        return ParsedRow(
            csv_title=title,
            series_id=title,
            volume=None,
            publisher="",
            authors=authors or [],
            asin=asin,
        )

    def test_digitalとmonthlyをASINでマージする(self):
        digital = {"B001": _LookupEntry(asin="B001", title="本A")}
        monthly = [self._row("B002", "本B", ["著者X"])]
        result = _build_lookup(digital, monthly)
        assert "B001" in result
        assert "B002" in result

    def test_月別CSVがdigitalの著者を補完する(self):
        digital = {"B001": _LookupEntry(asin="B001", title="本A", authors=[])}
        monthly = [self._row("B001", "本A", ["著者A"])]
        result = _build_lookup(digital, monthly)
        assert result["B001"].authors == ["著者A"]

    def test_既存著者は上書きされない(self):
        digital = {"B001": _LookupEntry(asin="B001", title="本A", authors=["既存著者"])}
        monthly = [self._row("B001", "本A", ["別著者"])]
        result = _build_lookup(digital, monthly)
        assert result["B001"].authors == ["既存著者"]

    def test_ASINなしの月別行はスキップされる(self):
        digital = {}
        monthly = [self._row("", "タイトルのみ")]
        result = _build_lookup(digital, monthly)
        assert len(result) == 0

    def test_月別CSVの重複ASINは最初の1件のみ採用(self):
        digital = {}
        monthly = [
            self._row("B003", "本C", ["著者1"]),
            self._row("B003", "本C2", ["著者2"]),
        ]
        result = _build_lookup(digital, monthly)
        assert result["B003"].authors == ["著者1"]


# ---------------------------------------------------------------------------
# _match
# ---------------------------------------------------------------------------

class TestMatch:
    def _entry(self, asin: str, title: str) -> _LookupEntry:
        return _LookupEntry(asin=asin, title=title)

    def test_既存ASINで直接マッチする(self):
        lookup = {"B001": self._entry("B001", "ワンピース")}
        norm_index = [("ワンピース", lookup["B001"])]
        existing = {"asin": "B001"}
        result = _match("book.pdf", existing, lookup, norm_index)
        assert result is not None
        assert result.asin == "B001"

    def test_ファイル名ステムでタイトルマッチする(self):
        entry = self._entry("B002", "鬼滅の刃")
        lookup = {"B002": entry}
        norm_index = [("鬼滅の刃", entry)]
        result = _match("鬼滅の刃 1.pdf", {}, lookup, norm_index)
        assert result is not None
        assert result.asin == "B002"

    def test_マッチなしはNoneを返す(self):
        lookup = {"B003": self._entry("B003", "全然違うタイトル")}
        norm_index = [("全然違うタイトル", lookup["B003"])]
        result = _match("本A.pdf", {}, lookup, norm_index)
        assert result is None

    def test_既存ASINがlookupにない場合はタイトルマッチにフォールバック(self):
        entry = self._entry("B004", "進撃の巨人")
        lookup = {"B004": entry}
        norm_index = [("進撃の巨人", entry)]
        existing = {"asin": "B999"}  # lookupに存在しないASIN
        result = _match("進撃の巨人 1.pdf", existing, lookup, norm_index)
        assert result is not None
        assert result.asin == "B004"


# ---------------------------------------------------------------------------
# run_import
# ---------------------------------------------------------------------------

class TestRunImport:
    def test_不正sourceはValueErrorを送出する(self):
        # run_import は source を直接チェックしないがルーターで制御
        # ここでは CSV ファイルが存在しない場合の ValueError をテスト
        with patch("services.amazon_csv_importer._DIGITAL_ORDERS_PATH", Path("/nonexistent/path.csv")):
            with patch("services.amazon_csv_importer._MONTHLY_CSV_DIR", Path("/nonexistent/dir/")):
                with pytest.raises(ValueError, match="Amazon CSV が見つかりません"):
                    run_import("novel")

    def test_CSVがある場合にupdate_meta_lockedが呼ばれる(self, tmp_path):
        # digital CSV を tmp_path に作成
        digital_dir = tmp_path / "amazon-order" / "Your Amazon Orders"
        digital_dir.mkdir(parents=True)
        digital_csv = digital_dir / "Digital Content Orders.csv"

        fields = ["Order ID", "ASIN", "Digital Order Item ID", "Product Name",
                  "Subscription Order Type", "Seller of Record"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        writer.writerow({
            "Order ID": "D01", "ASIN": "B001234567",
            "Digital Order Item ID": "doi1", "Product Name": "テスト書籍",
            "Subscription Order Type": "", "Seller of Record": "",
        })
        digital_csv.write_text(buf.getvalue(), encoding="utf-8-sig")

        captured_meta = {}

        def fake_update(source, updater):
            meta = {"テスト書籍.pdf": {}}
            updater(meta)
            captured_meta.update(meta)

        with patch("services.amazon_csv_importer._DIGITAL_ORDERS_PATH", digital_csv):
            with patch("services.amazon_csv_importer._MONTHLY_CSV_DIR", tmp_path / "monthly"):
                with patch("services.amazon_csv_importer.update_meta_locked", side_effect=fake_update):
                    result = run_import("novel")

        assert isinstance(result, ImportResult)

    def test_既存authorsとasinがある場合はskipされる(self, tmp_path):
        digital_dir = tmp_path / "amazon-order" / "Your Amazon Orders"
        digital_dir.mkdir(parents=True)
        digital_csv = digital_dir / "Digital Content Orders.csv"

        fields = ["Order ID", "ASIN", "Digital Order Item ID", "Product Name",
                  "Subscription Order Type", "Seller of Record"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        writer.writerow({
            "Order ID": "D01", "ASIN": "B001",
            "Digital Order Item ID": "doi1", "Product Name": "テスト書籍",
            "Subscription Order Type": "", "Seller of Record": "",
        })
        digital_csv.write_text(buf.getvalue(), encoding="utf-8-sig")

        def fake_update(source, updater):
            # すでに authors と asin が揃っている
            meta = {"テスト書籍.pdf": {"authors": ["既存著者"], "asin": "B001"}}
            updater(meta)

        with patch("services.amazon_csv_importer._DIGITAL_ORDERS_PATH", digital_csv):
            with patch("services.amazon_csv_importer._MONTHLY_CSV_DIR", tmp_path / "monthly"):
                with patch("services.amazon_csv_importer.update_meta_locked", side_effect=fake_update):
                    result = run_import("novel")

        assert result.skipped == 1
        assert result.updated == 0
