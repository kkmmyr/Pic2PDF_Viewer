"""Kindle 価格監視のサービス/API 契約テスト。"""

from unittest.mock import patch

import pytest

from services.kindle_catalog.migrations import upgrade_head
from services.kindle_catalog.price_watch import (
    create_watch,
    list_history,
    normalize_amazon_url,
    record_observation,
)


def test_normalize_amazon_url_accepts_product_path_and_removes_tracking():
    url, asin = normalize_amazon_url("https://www.amazon.co.jp/-/en/dp/B012345678/ref=abc?tag=test")

    assert url == "https://www.amazon.co.jp/dp/B012345678"
    assert asin == "B012345678"


def test_normalize_amazon_url_rejects_non_amazon_or_missing_asin():
    with pytest.raises(ValueError):
        normalize_amazon_url("https://example.com/dp/B012345678")
    with pytest.raises(ValueError):
        normalize_amazon_url("https://www.amazon.co.jp/s?k=kindle")


def test_price_observation_notifies_on_first_threshold_crossing_and_later_drop(tmp_data_dir):
    upgrade_head()
    watch = create_watch(
        url="https://www.amazon.co.jp/dp/B012345678",
        threshold_percent=50,
    )

    with patch(
        "services.kindle_catalog.price_watch.price_notify.notify_price_event",
        return_value=True,
    ) as notify:
        first = record_observation(
            watch_id=watch["id"],
            current_price=400,
            list_price=1000,
            title="テスト本",
        )
        same_price = record_observation(
            watch_id=watch["id"],
            current_price=400,
            list_price=1000,
        )
        dropped = record_observation(
            watch_id=watch["id"],
            current_price=300,
            list_price=1000,
        )

    assert first["observation"]["ratio_percent"] == 40.0
    assert first["below_threshold"] is True
    assert first["notifications"] == [{"kind": "below_threshold", "sent": True}]
    assert same_price["price_dropped"] is False
    assert same_price["notifications"] == []
    assert dropped["price_dropped"] is True
    assert dropped["notifications"] == [{"kind": "price_drop", "sent": True}]
    assert notify.call_count == 2
    assert len(list_history(watch["id"])) == 3


def test_partial_observation_fails_closed_without_threshold_notification(tmp_data_dir):
    upgrade_head()
    watch = create_watch(url="https://www.amazon.co.jp/dp/B012345678")

    with patch(
        "services.kindle_catalog.price_watch.price_notify.notify_price_event",
        return_value=True,
    ) as notify:
        result = record_observation(
            watch_id=watch["id"],
            current_price=400,
            list_price=None,
            status="partial",
            error_message="定価/参考価格を読み取れませんでした",
        )

    assert result["observation"]["status"] == "partial"
    assert result["observation"]["ratio_percent"] is None
    assert result["below_threshold"] is False
    assert result["notifications"] == []
    notify.assert_not_called()


def test_price_watch_api_crud_and_observation(client):
    upgrade_head()
    response = client.post(
        "/api/kindle-price-watches",
        json={
            "url": "https://www.amazon.co.jp/dp/B012345678/ref=tracking",
            "title": "APIテスト本",
            "threshold_percent": 60,
        },
    )
    assert response.status_code == 201
    watch = response.json()
    assert watch["url"] == "https://www.amazon.co.jp/dp/B012345678"
    assert watch["threshold_percent"] == 60.0

    list_response = client.get("/api/kindle-price-watches")
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == watch["id"]

    observation = client.post(
        f"/api/kindle-price-watches/{watch['id']}/observations",
        json={"current_price": 500, "list_price": 1000},
    )
    assert observation.status_code == 200
    assert observation.json()["observation"]["ratio_percent"] == 50.0

    update = client.patch(
        f"/api/kindle-price-watches/{watch['id']}",
        json={"enabled": False},
    )
    assert update.status_code == 200
    assert update.json()["enabled"] is False

    delete = client.delete(f"/api/kindle-price-watches/{watch['id']}")
    assert delete.status_code == 200
    assert delete.json() == {"id": watch["id"], "deleted": True}
