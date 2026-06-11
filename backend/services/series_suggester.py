"""既存シリーズへの紐付け候補を提案する純関数群（A-1）。

シリーズ自動グループ化（Phase 6 で撤去）の代替。書籍タイトルと既存シリーズの
類似度を**ルールベース**でスコア化し、上位候補を返す。書き込み副作用なし。

UI 側で「ユーザーが選んだ複数冊」に対する「既存シリーズへの紐付け候補」として
表示し、ユーザーが確定操作した場合のみ既存の `POST /api/series/assign` で
書き込みが行われる。
"""

import re
from typing import TypedDict

from services.meta_store import MetaDict, make_key
from services.series_detector import authors_key

SUGGEST_MIN_SCORE = 0.4
SUGGEST_MAX_CANDIDATES = 5
AUTHOR_MATCH_BONUS = 0.2


class SuggestedSeries(TypedDict):
    series_id: str
    series_title: str
    series_max_index: float
    score: float
    reason: str


def _common_prefix_len(a: str, b: str) -> int:
    """2 文字列の共通前方プレフィックス長を返す。"""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


_VOLUME_SUFFIX_RE = re.compile(
    r"[\s 　_\-]*("
    r"第?\s*\d+(?:\.\d+)?\s*巻?"  # 整数/小数（前置「第」・後置「巻」許容）
    r"|第?[一二三四五六七八九十百]+巻?"  # 漢数字
    r"|[vV][oO][lL]\.?\s*\d+(?:\.\d+)?"  # vol.N
    r"|[(（][上中下前後]+[)）]"  # (上中下)
    r")?[\s 　巻]*$"
)


def _strip_volume_suffix(title: str) -> str:
    """シリーズ表示名末尾の巻数表記を除いた本体を返す。

    例:
        "鬼滅の刃 1巻"  -> "鬼滅の刃"
        "進撃の巨人 03"  -> "進撃の巨人"
        "○○ vol.4"     -> "○○"
    """
    return _VOLUME_SUFFIX_RE.sub("", title.strip()).strip()


class _SeriesInfo(TypedDict):
    series_id: str
    series_title: str
    max_index: float
    authors_set: frozenset[str]


def _aggregate_existing_series(meta: MetaDict) -> dict[str, _SeriesInfo]:
    """meta から既存シリーズの情報を集計。

    Returns:
        `{ series_id: { series_id, series_title, max_index, authors_set } }`。
        作者は「同シリーズに属する書籍に共通して出現する作者集合」を取る
        （シリーズ内で作者がブレている可能性は低いが、最初に見つかったものを採用）。
    """
    result: dict[str, _SeriesInfo] = {}
    for entry in meta.values():
        sid = entry.get("series_id")
        if not sid:
            continue
        idx = float(entry.get("series_index", 0))
        existing = result.get(sid)
        if existing is None:
            result[sid] = {
                "series_id": sid,
                "series_title": entry.get("series_title", ""),
                "max_index": idx,
                "authors_set": frozenset(authors_key(entry.get("authors", []))),
            }
        else:
            if idx > existing["max_index"]:
                existing["max_index"] = idx
    return result


def suggest_series(
    meta: MetaDict,
    path: str,
    names: list[str],
) -> list[SuggestedSeries]:
    """選択書籍に対する既存シリーズの紐付け候補を返す。

    Args:
        meta: 全 meta データ
        path: 書籍の親ディレクトリ
        names: 選択された書籍ファイル名のリスト

    Returns:
        スコア降順で最大 `SUGGEST_MAX_CANDIDATES` 件。閾値 `SUGGEST_MIN_SCORE`
        未満は除外。
    """
    if not names:
        return []

    # 選択書籍のタイトル（拡張子なし）と作者集合
    selected_books: list[tuple[str, frozenset[str]]] = []
    for name in names:
        key = make_key(path, name)
        entry = meta.get(key, {})
        title_no_ext = name.rsplit(".", 1)[0] if "." in name else name
        authors_set = frozenset(authors_key(entry.get("authors", [])))
        selected_books.append((title_no_ext, authors_set))

    series_infos = _aggregate_existing_series(meta)
    if not series_infos:
        return []

    candidates: list[SuggestedSeries] = []
    for info in series_infos.values():
        normalized_title = _strip_volume_suffix(info["series_title"]) or info["series_title"]
        if not normalized_title:
            continue

        # 各選択書籍とのスコアを平均する
        scores: list[float] = []
        author_match_count = 0
        for book_title, book_authors in selected_books:
            min_len = min(len(book_title), len(normalized_title))
            if min_len == 0:
                continue
            prefix_len = _common_prefix_len(book_title, normalized_title)
            scores.append(prefix_len / min_len)
            if book_authors and book_authors == info["authors_set"]:
                author_match_count += 1

        if not scores:
            continue
        avg_score = sum(scores) / len(scores)
        # 全書籍で作者集合が一致した場合のみ加点
        author_bonus = AUTHOR_MATCH_BONUS if author_match_count == len(selected_books) else 0.0
        final_score = min(1.0, avg_score + author_bonus)

        if final_score < SUGGEST_MIN_SCORE:
            continue

        reasons = ["title_match"]
        if author_match_count == len(selected_books):
            reasons.append("author_match")

        candidates.append(
            {
                "series_id": info["series_id"],
                "series_title": info["series_title"],
                "series_max_index": info["max_index"],
                "score": round(final_score, 4),
                "reason": ",".join(reasons),
            }
        )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:SUGGEST_MAX_CANDIDATES]
