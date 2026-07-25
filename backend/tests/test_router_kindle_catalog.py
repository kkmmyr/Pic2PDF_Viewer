"""Kindle 購入カタログ API の契約テスト。"""

from unittest.mock import patch

from services.kindle_catalog.migrations import upgrade_head


def test_list_books_response_model(client):
    upgrade_head()
    response = client.get("/api/kindle-catalog/books")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 50}


def test_migration_preview_hides_source_path(client):
    with patch(
        "services.kindle_catalog.legacy_migration.preview",
        return_value={
            "configured": True,
            "source_name": "kindle.db",
            "source_size": 123,
            "fingerprint": "a" * 64,
            "integrity": "ok",
            "counts": {"books": 1},
            "excluded_counts": {"book_reviews": 2},
            "missing_asin": 0,
            "confirmation_token": "token",
            "expires_at": "2026-07-25T12:00:00+09:00",
            "images_migrated": False,
        },
    ):
        response = client.post("/api/kindle-catalog/migration/preview")

    assert response.status_code == 200
    assert response.json()["source_name"] == "kindle.db"
    assert "source_path" not in response.json()
    assert response.json()["images_migrated"] is False
