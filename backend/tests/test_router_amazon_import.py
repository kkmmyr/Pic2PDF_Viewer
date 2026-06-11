"""routers/amazon_import.py のテスト。"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _mock_run_import(updated=0, skipped=0, unmatched=0):
    from services.amazon_csv_importer import ImportResult

    return ImportResult(updated=updated, skipped=skipped, unmatched=unmatched)


class TestAmazonCsvImport:
    def test_正常リクエストでupdated件数を返す(self):
        with patch(
            "routers.amazon_import.run_import", return_value=_mock_run_import(updated=3, skipped=1, unmatched=2)
        ):
            resp = client.post("/api/amazon/import?source=novel")
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] == 3
        assert body["skipped"] == 1
        assert body["unmatched"] == 2

    def test_comicソースも受け付ける(self):
        with patch("routers.amazon_import.run_import", return_value=_mock_run_import()):
            resp = client.post("/api/amazon/import?source=comic")
        assert resp.status_code == 200

    def test_不正sourceは400を返す(self):
        resp = client.post("/api/amazon/import?source=doujin")
        assert resp.status_code == 400
        assert "novel" in resp.json()["detail"] or "comic" in resp.json()["detail"]

    def test_未指定sourceはデフォルトで動作する(self):
        with patch("routers.amazon_import.run_import", return_value=_mock_run_import()):
            resp = client.post("/api/amazon/import")
        assert resp.status_code == 200

    def test_CSVが見つからない場合は422を返す(self):
        with patch("routers.amazon_import.run_import", side_effect=ValueError("Amazon CSV が見つかりません")):
            resp = client.post("/api/amazon/import?source=novel")
        assert resp.status_code == 422
        assert "Amazon CSV" in resp.json()["detail"]
