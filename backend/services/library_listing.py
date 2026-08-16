"""画像ディレクトリ起点の書籍一覧走査と短命キャッシュ。"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

from natsort import natsorted

from config import SourceDirs
from utils.file_naming import get_thumbnail_name
from utils.file_utils import is_image_file
from utils.path_utils import join_path, resolve_under_base

LibraryFile = dict[str, str | int | None]
LibraryListing = dict[str, list[LibraryFile] | str]
ThumbnailScheduler = Callable[[str, str], None]
CacheKey = tuple[str, str]


@dataclass(frozen=True)
class DirectorySignature:
    image_dir: str
    image_mtime_ns: int | None
    thumbnail_dir: str
    thumbnail_mtime_ns: int | None


@dataclass
class _CacheEntry:
    signature: DirectorySignature
    created_at: float
    listing: LibraryListing


def _copy_listing(listing: LibraryListing) -> LibraryListing:
    files = listing["files"]
    assert isinstance(files, list)
    return {
        "files": [dict(item) for item in files],
        "current_path": str(listing["current_path"]),
    }


class LibraryListingCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = 30.0,
        max_entries: int = 128,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[CacheKey, _CacheEntry] = OrderedDict()
        self._lock = threading.RLock()

    def get_or_build(
        self,
        key: CacheKey,
        signature: DirectorySignature,
        builder: Callable[[], LibraryListing],
    ) -> LibraryListing:
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.signature == signature and now - entry.created_at < self._ttl_seconds:
                self._entries.move_to_end(key)
                return _copy_listing(entry.listing)

            listing = builder()
            self._entries[key] = _CacheEntry(signature, now, _copy_listing(listing))
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
            return _copy_listing(listing)

    def invalidate(self, source: str | None = None, path: str | None = None) -> None:
        with self._lock:
            if source is None:
                self._entries.clear()
                return
            keys = [key for key in self._entries if key[0] == source and (path is None or key[1] == path)]
            for key in keys:
                self._entries.pop(key, None)


def _mtime_ns(path: str) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except FileNotFoundError:
        return None


def _signature(image_dir: str, thumbnail_dir: str) -> DirectorySignature:
    return DirectorySignature(
        image_dir=os.path.abspath(image_dir),
        image_mtime_ns=_mtime_ns(image_dir),
        thumbnail_dir=os.path.abspath(thumbnail_dir),
        thumbnail_mtime_ns=_mtime_ns(thumbnail_dir),
    )


def _scan_library(
    path: str,
    dirs: SourceDirs,
    target_img_dir: str,
    target_thumb_dir: str,
    schedule_thumbnail: ThumbnailScheduler,
) -> LibraryListing:
    if not os.path.exists(target_img_dir):
        return {"files": [], "current_path": path}
    if not os.path.isdir(target_img_dir):
        raise NotADirectoryError(target_img_dir)

    files: list[LibraryFile] = []
    for item in os.listdir(target_img_dir):
        item_path = join_path(target_img_dir, item)
        if not os.path.isdir(item_path):
            continue
        images = natsorted(name for name in os.listdir(item_path) if is_image_file(name))
        if not images:
            continue

        pdf_name = f"{item}.pdf"
        thumb_name = get_thumbnail_name(pdf_name)
        thumb_path = join_path(target_thumb_dir, thumb_name)
        thumbnail: str | None = None
        if os.path.exists(thumb_path):
            relative = join_path(path, thumb_name) if path else thumb_name
            encoded = "/".join(quote(segment, safe="") for segment in relative.replace(os.sep, "/").split("/"))
            thumbnail = f"{dirs['thumb_url_prefix']}/{encoded}"
        else:
            schedule_thumbnail(join_path(item_path, images[0]), thumb_path)

        files.append(
            {
                "name": pdf_name,
                "thumbnail": thumbnail,
                "created_at": int(os.path.getctime(item_path)),
            }
        )

    return {"files": files, "current_path": path}


_cache = LibraryListingCache()


def list_library_books(
    source: str,
    path: str,
    dirs: SourceDirs,
    schedule_thumbnail: ThumbnailScheduler,
) -> LibraryListing:
    target_img_dir = resolve_under_base(dirs["img"], path)
    target_thumb_dir = resolve_under_base(dirs["thumb"], path)
    signature = _signature(target_img_dir, target_thumb_dir)
    return _cache.get_or_build(
        (source, path),
        signature,
        lambda: _scan_library(path, dirs, target_img_dir, target_thumb_dir, schedule_thumbnail),
    )


def invalidate_library_listing(source: str | None = None, path: str | None = None) -> None:
    _cache.invalidate(source, path)
