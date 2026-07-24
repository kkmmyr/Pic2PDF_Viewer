"""services.hitomi.arrival_store のSQLite永続化テスト。"""

import json

import pytest

from services.hitomi import arrival_store


@pytest.fixture(autouse=True)
def patch_meta_dir(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "META_DB_DIR", str(tmp_path / "meta"))


def _item(gallery_id: int, *, is_read: bool = False) -> arrival_store.ArrivalItem:
    return {
        "id": gallery_id,
        "artist": "artist",
        "display_artist": "Artist",
        "title": f"title-{gallery_id}",
        "language": "japanese",
        "type": "manga",
        "page_count": 20,
        "published_at": "2026-05-01",
        "discovered_at": f"2026-05-{gallery_id:02d}T10:00:00+09:00",
        "url": f"https://hitomi.la/galleries/{gallery_id}.html",
        "is_read": is_read,
    }


class TestMergeAndList:
    def test_adds_and_ignores_duplicate_ids(self):
        assert arrival_store.merge_new_items([_item(1), _item(2), _item(1)]) == 2

        page = arrival_store.list_arrivals("unread", 0, 60)
        assert [item["id"] for item in page["items"]] == [2, 1]
        assert page["unread_count"] == 2

    def test_filters_and_pages(self):
        arrival_store.merge_new_items([_item(1), _item(2), _item(3)])
        assert arrival_store.dismiss(2) is True

        read_page = arrival_store.list_arrivals("read", 0, 60)
        unread_page = arrival_store.list_arrivals("unread", 1, 1)
        assert [item["id"] for item in read_page["items"]] == [2]
        assert [item["id"] for item in unread_page["items"]] == [1]
        assert unread_page["total"] == 2


class TestDismiss:
    def test_dismiss_records_timestamp_and_is_idempotent(self):
        arrival_store.merge_new_items([_item(1)])

        assert arrival_store.dismiss(1) is True
        assert arrival_store.dismiss(1) is False
        item = arrival_store.list_arrivals("read", 0, 1)["items"][0]
        assert item["read_at"] is not None

    def test_dismiss_all_updates_unread_only(self):
        arrival_store.merge_new_items([_item(1), _item(2), _item(3)])
        arrival_store.dismiss(2)

        assert arrival_store.dismiss_all() == 2
        assert arrival_store.list_arrivals("read", 0, 60)["read_count"] == 3


class TestLegacyImport:
    def test_imports_existing_read_state_without_fabricating_read_at(self, tmp_path):
        data_dir = tmp_path / "hitomi"
        data_dir.mkdir()
        payload = {"items": [{**_item(1), "dismissed": True}, {**_item(2), "dismissed": False}]}
        (data_dir / "new_arrivals.json").write_text(json.dumps(payload), encoding="utf-8")

        assert arrival_store.import_legacy_json(data_dir) == 2
        assert arrival_store.import_legacy_json(data_dir) == 0
        read_item = arrival_store.list_arrivals("read", 0, 60)["items"][0]
        assert read_item["id"] == 1
        assert read_item["read_at"] is None

    def test_legacy_import_does_not_overwrite_database_state(self, tmp_path):
        arrival_store.merge_new_items([_item(1)])
        arrival_store.dismiss(1)
        data_dir = tmp_path / "hitomi"
        data_dir.mkdir()
        (data_dir / "new_arrivals.json").write_text(
            json.dumps({"items": [{**_item(1), "dismissed": False}]}),
            encoding="utf-8",
        )

        assert arrival_store.import_legacy_json(data_dir) == 0
        assert arrival_store.list_arrivals("read", 0, 60)["total"] == 1
