"""シリーズ手動編集 API 用ヘルパー。

シリーズ自動グループ化（Phase 6 で撤去）で使われていた判定関数群は削除し、
手動編集 API（POST /api/series/assign 等）で使う `authors_key` /
`stable_series_id` のみを残置している。
"""

import hashlib


def authors_key(authors: list[str]) -> tuple[str, ...]:
    """作者リストを順序非依存の集合キーに変換する。"""
    return tuple(sorted({a.strip() for a in authors if a.strip()}))


def stable_series_id(prefix: str, authors_key_value: tuple[str, ...]) -> str:
    """共通プレフィックス + 作者集合から安定したシリーズ ID を作る。"""
    raw = prefix + "\x00" + "\x00".join(authors_key_value)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
