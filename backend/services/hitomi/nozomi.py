"""hitomi.la NOZOMI ファイルの取得とパース。

NOZOMI は hitomi.la が事前生成しているバイナリ形式の「条件にマッチする
ギャラリー ID 配列」（big-endian 32bit int の連続）。詳細仕様は
docs/03_詳細設計/hitomi新着監視設計書.md §8 を参照。
"""
from __future__ import annotations

import struct
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


def _build_nozomi_url(artist_normalized: str, language: str) -> str:
    return f"{NOZOMI_BASE}/{artist_normalized}-{language}.nozomi"


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
    url = _build_nozomi_url(artist_normalized, language)
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

    return parse_nozomi_bytes(r.content)


def check_nozomi_exists(
    artist_normalized: str,
    language: str = "japanese",
    *,
    client: httpx.Client | None = None,
) -> bool:
    """指定作者の NOZOMI が存在するか HEAD でチェックする（watchlist 登録時の検証用）。"""
    url = _build_nozomi_url(artist_normalized, language)
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
