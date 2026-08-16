"""services.library_listing の短命LRU cache契約。"""

from typing import cast

from services.library_listing import DirectorySignature, LibraryListing, LibraryListingCache


def _listing(name: str) -> LibraryListing:
    return {
        "files": [{"name": name, "thumbnail": None, "created_at": 1}],
        "current_path": "",
    }


def _files(listing: LibraryListing) -> list[dict[str, str | int | None]]:
    return cast(list[dict[str, str | int | None]], listing["files"])


def _signature(version: int = 1) -> DirectorySignature:
    return DirectorySignature("images", version, "thumbnails", version)


def test_cache_hit_reuses_builder_and_returns_copy() -> None:
    now = [0.0]
    calls: list[int] = []
    cache = LibraryListingCache(clock=lambda: now[0])

    def build() -> LibraryListing:
        calls.append(1)
        return _listing("book.pdf")

    first = cache.get_or_build(("doujin", ""), _signature(), build)
    _files(first)[0]["name"] = "changed.pdf"
    second = cache.get_or_build(("doujin", ""), _signature(), build)

    assert calls == [1]
    assert _files(second)[0]["name"] == "book.pdf"


def test_cache_rebuilds_after_ttl_or_signature_change() -> None:
    now = [0.0]
    calls: list[int] = []
    cache = LibraryListingCache(ttl_seconds=30, clock=lambda: now[0])

    def build() -> LibraryListing:
        calls.append(1)
        return _listing(f"book-{len(calls)}.pdf")

    cache.get_or_build(("doujin", ""), _signature(), build)
    now[0] = 30.0
    cache.get_or_build(("doujin", ""), _signature(), build)
    cache.get_or_build(("doujin", ""), _signature(2), build)

    assert len(calls) == 3


def test_invalidate_is_scoped_by_source_and_path() -> None:
    calls: list[str] = []
    cache = LibraryListingCache()

    def build(name: str) -> LibraryListing:
        calls.append(name)
        return _listing(name)

    cache.get_or_build(("doujin", ""), _signature(), lambda: build("doujin-root"))
    cache.get_or_build(("doujin", "child"), _signature(), lambda: build("doujin-child"))
    cache.get_or_build(("comic", ""), _signature(), lambda: build("comic-root"))

    cache.invalidate("doujin", "")
    cache.get_or_build(("doujin", ""), _signature(), lambda: build("doujin-root-2"))
    cache.get_or_build(("doujin", "child"), _signature(), lambda: build("unexpected-child"))
    cache.get_or_build(("comic", ""), _signature(), lambda: build("unexpected-comic"))

    assert calls == ["doujin-root", "doujin-child", "comic-root", "doujin-root-2"]


def test_lru_evicts_oldest_entry() -> None:
    calls: list[str] = []
    cache = LibraryListingCache(max_entries=2)

    def build(name: str) -> LibraryListing:
        calls.append(name)
        return _listing(name)

    cache.get_or_build(("doujin", "a"), _signature(), lambda: build("a"))
    cache.get_or_build(("doujin", "b"), _signature(), lambda: build("b"))
    cache.get_or_build(("doujin", "c"), _signature(), lambda: build("c"))
    cache.get_or_build(("doujin", "a"), _signature(), lambda: build("a-again"))

    assert calls == ["a", "b", "c", "a-again"]
