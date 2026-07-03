"""hitomi.la NOZOMI ファイルの取得とパース。

NOZOMI は hitomi.la が事前生成しているバイナリ形式の「条件にマッチする
ギャラリー ID 配列」（big-endian 32bit int の連続）。詳細仕様は
docs/design/詳細設計/機能別/hitomi新着監視設計書.md §8 を参照。
"""

from __future__ import annotations

import struct
import urllib.parse
from typing import Final

import httpx

NOZOMI_BASE: Final[str] = "https://ltn.gold-usergeneratedcontent.net/n/artist"
USER_AGENT: Final[str] = "Pic2PDF-Hitomi-Monitor/1.0"
DEFAULT_TIMEOUT: Final[float] = 10.0


class HitomiError(Exception):
    """Base error for hitomi services."""


class HitomiArtistNotFoundError(HitomiError):
    """The artist NOZOMI URL returned 404."""


class HitomiNetworkError(HitomiError):
    """Network or HTTP error fetching NOZOMI."""


def parse_nozomi_bytes(data: bytes) -> list[int]:
    """big-endian 32bit int 配列としてデコード。4 バイト境界で切り捨て。"""
    usable = len(data) - (len(data) % 4)
    if usable == 0:
        return []
    return list(struct.unpack(f">{usable // 4}I", data[:usable]))


def diff_unseen_ids(top_ids: list[int], prev_top: int | None) -> list[int]:
    """前回の top_id より新しい ID を返す。

    NOZOMI は新着順（先頭が最新）。前回 top と一致する位置で停止し、
    それより前にあった ID を新着とみなす。
    """
    if prev_top is None:
        return list(top_ids)
    out: list[int] = []
    for gid in top_ids:
        if gid == prev_top:
            break
        out.append(gid)
    return out


def build_nozomi_url(artist_key: str, language: str) -> str:
    """`artist_key`（`_` 区切りの内部識別子）から NOZOMI URL を構築する。

    hitomi.la の NOZOMI ファイル名は **空白を含む**（例: `aka shio-japanese.nozomi`）。
    内部 key の `_` は意味的に空白を表すため、URL 構築時は空白に戻してから URL encode
    する。結果として URL では `%20` が現れる（例: `aka_shio` → `aka%20shio`）。

    `-` は NOZOMI ファイル名のセパレータと衝突しないので safe にしない。
    """
    artist_part = artist_key.replace("_", " ")
    artist_url = urllib.parse.quote(artist_part, safe="")
    return f"{NOZOMI_BASE}/{artist_url}-{language}.nozomi"


def fetch_nozomi_head(
    artist_normalized: str,
    language: str = "japanese",
    count: int = 20,
    *,
    client: httpx.Client | None = None,
) -> list[int]:
    """NOZOMI ファイル先頭 N 件の ID を取得する。

    Range リクエストで count*4 バイトのみ取得し、big-endian 32bit int をデコード。
    """
    url = build_nozomi_url(artist_normalized, language)
    end = count * 4 - 1
    headers = {"Range": f"bytes=0-{end}", "User-Agent": USER_AGENT}

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT)
    assert client is not None
    try:
        try:
            r = client.get(url, headers=headers)
        except httpx.HTTPError as e:
            raise HitomiNetworkError(f"NOZOMI fetch failed: {e}") from e
    finally:
        if owns_client:
            client.close()

    if r.status_code == 404:
        raise HitomiArtistNotFoundError(f"NOZOMI not found: {url}")
    if r.status_code not in (200, 206):
        raise HitomiNetworkError(f"NOZOMI fetch returned {r.status_code} for {url}")

    # サーバーが Range を無視して 200 (フルコンテンツ) を返すことがあるため、
    # 常に要求した count*4 バイトへスライスしてから渡す。
    return parse_nozomi_bytes(r.content[: count * 4])


def check_nozomi_exists(
    artist_normalized: str,
    language: str = "japanese",
    *,
    client: httpx.Client | None = None,
) -> bool:
    """指定作者の NOZOMI が存在するか HEAD でチェックする（watchlist 登録時の検証用）。"""
    url = build_nozomi_url(artist_normalized, language)
    headers = {"User-Agent": USER_AGENT}

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT)
    assert client is not None
    try:
        try:
            r = client.head(url, headers=headers)
        except httpx.HTTPError as e:
            raise HitomiNetworkError(f"NOZOMI head check failed: {e}") from e
    finally:
        if owns_client:
            client.close()

    return r.status_code == 200
