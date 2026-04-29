"""hitomi.la 個別ギャラリーのメタデータ取得。

`/galleries/<id>.js` は冒頭に `var galleryinfo = {...};` の形式で
JSON が埋め込まれた JavaScript ファイル。プレフィックスを除いて JSON.parse する。
"""
from __future__ import annotations

import json
import re
from typing import Any, Final

import httpx

from .nozomi import (
    DEFAULT_TIMEOUT,
    USER_AGENT,
    HitomiError,
    HitomiNetworkError,
)

METADATA_BASE: Final[str] = "https://ltn.gold-usergeneratedcontent.net/galleries"

_PREFIX_RE: Final = re.compile(r"^\s*var\s+galleryinfo\s*=\s*", re.DOTALL)


class HitomiMetadataError(HitomiError):
    """Failed to parse galleryinfo metadata."""


def parse_galleryinfo(js_text: str) -> dict[str, Any]:
    """`var galleryinfo = {...};` から JSON 部分を抽出してパース。"""
    m = _PREFIX_RE.match(js_text)
    if not m:
        raise HitomiMetadataError("'var galleryinfo = ' prefix not found")
    rest = js_text[m.end():].strip()
    if rest.endswith(";"):
        rest = rest[:-1].rstrip()
    try:
        return json.loads(rest)
    except json.JSONDecodeError as e:
        raise HitomiMetadataError(f"galleryinfo JSON parse failed: {e}") from e


def fetch_metadata(
    gallery_id: int,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """`/galleries/<id>.js` を取得しパースする。

    主要フィールド: `id`, `title`, `artists[]`, `language`, `type`, `date`, `files[]`
    """
    url = f"{METADATA_BASE}/{gallery_id}.js"
    headers = {"User-Agent": USER_AGENT}

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT)
    assert client is not None
    try:
        try:
            r = client.get(url, headers=headers)
        except httpx.HTTPError as e:
            raise HitomiNetworkError(f"metadata fetch failed: {e}") from e
    finally:
        if owns_client:
            client.close()

    if r.status_code != 200:
        raise HitomiNetworkError(
            f"metadata fetch returned {r.status_code} for id={gallery_id}"
        )

    return parse_galleryinfo(r.text)
