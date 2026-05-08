"""シリーズ判定の純関数群。

`series_resolver.py` のジョブ実行ロジック（state 管理・スレッド起動・Gemma 補助）から
分離した、状態を持たない判定関数。タイトル前方一致 + 巻数パターンによる
シリーズ検出と、meta からのシリーズメンバー集計を担当する。
"""
import hashlib
import os
from typing import Literal, TypedDict

from config import get_dirs_by_source
from services.meta_store import MetaDict, make_key
from services.volume_parser import parse_pair_volume_indexes
from utils.file_utils import is_pdf_file

SERIES_MIN_PREFIX_LEN = 5
# A-6: 未分類候補レポート用、自動判定よりゆるい下限（短すぎてカットされたペアを拾う）
SERIES_CANDIDATE_MIN_PREFIX_LEN = 3
SERIES_UNRESOLVED_MAX_CANDIDATES = 200

UnresolvedReason = Literal["short_prefix", "volume_parse_failed"]


class CandidateBook(TypedDict):
    path: str
    name: str
    title: str


class UnresolvedCandidate(TypedDict):
    reason: UnresolvedReason
    score: float
    common_prefix: str
    books: list[CandidateBook]


def common_prefix(a: str, b: str) -> str:
    """2 文字列の共通前方プレフィックスを返す。"""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return a[:i]
    return a[:n]


def authors_key(authors: list[str]) -> tuple[str, ...]:
    """作者リストを順序非依存の集合キーに変換する。"""
    return tuple(sorted({a.strip() for a in authors if a.strip()}))


def stable_series_id(prefix: str, authors_key_value: tuple[str, ...]) -> str:
    """共通プレフィックス + 作者集合から安定したシリーズ ID を作る。"""
    raw = prefix + "\x00" + "\x00".join(authors_key_value)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def trim_prefix(prefix: str) -> str:
    """シリーズ表示名として使うため、末尾の余分な空白・記号を除去する。"""
    return prefix.rstrip(" 　-_:：・")


def collect_books(source: str) -> list[tuple[str, str, str]]:
    """対象ソースの全 PDF を `(rel_path, filename, title)` のリストで返す。"""
    pdf_root = get_dirs_by_source(source)["pdf"]
    if not os.path.isdir(pdf_root):
        return []
    items: list[tuple[str, str, str]] = []
    for root, _, files in os.walk(pdf_root):
        for f in sorted(files):
            if not is_pdf_file(f):
                continue
            rel = os.path.relpath(root, pdf_root)
            rel_path = "" if rel == "." else rel.replace("\\", "/")
            title = os.path.splitext(f)[0]
            items.append((rel_path, f, title))
    return items


def group_by_authors(
    books: list[tuple[str, str, str]],
    meta: MetaDict,
) -> dict[tuple[str, ...], list[tuple[str, str, str]]]:
    """書籍を作者集合キーごとにグループ化する。作者なしは除外。"""
    groups: dict[tuple[str, ...], list[tuple[str, str, str]]] = {}
    for rel_path, filename, title in books:
        key = make_key(rel_path, filename)
        authors = meta.get(key, {}).get("authors") or []
        akey = authors_key(authors)
        if not akey:
            continue
        groups.setdefault(akey, []).append((rel_path, filename, title))
    return groups


def detect_series_in_group(
    group: list[tuple[str, str, str]],
) -> dict[str, tuple[str, float]]:
    """1 つの作者グループ内でシリーズ判定する。

    Returns:
        `{ make_key(rel_path, filename): (series_title, series_index) }` のマップ。
        `series_index` は float（小数巻 `2.5` 等に対応）。
    """
    result: dict[str, tuple[str, float]] = {}
    n = len(group)
    if n < 2:
        return result

    # 同じプレフィックスを共有するメンバーを集める。プレフィックスは
    # 「ペアごとに最大共通プレフィックス」を取ってから巻数判定が成立する組のみ採用。
    # 効率より分かりやすさ優先で全ペア O(n^2)。書籍数が数千以下なら問題ない。
    prefix_to_members: dict[str, list[tuple[str, str, float]]] = {}
    for i in range(n):
        for j in range(i + 1, n):
            ti, tj = group[i][2], group[j][2]
            prefix = common_prefix(ti, tj)
            if len(prefix) < SERIES_MIN_PREFIX_LEN:
                continue
            # 「巻数なし＝1巻」ルール込みで巻数解析
            idx_i, idx_j = parse_pair_volume_indexes(ti[len(prefix):], tj[len(prefix):])
            if idx_i is None or idx_j is None:
                continue
            display = trim_prefix(prefix)
            if not display:
                continue
            members = prefix_to_members.setdefault(display, [])
            for path, name, idx in [(group[i][0], group[i][1], idx_i), (group[j][0], group[j][1], idx_j)]:
                key = make_key(path, name)
                if not any(k == key for k, _, _ in members):
                    members.append((key, name, idx))

    # 同じ書籍が複数グループに属した場合は「最も長いプレフィックス」を採用
    best_for_key: dict[str, tuple[str, float]] = {}
    for prefix, members in prefix_to_members.items():
        for key, _name, idx in members:
            current = best_for_key.get(key)
            if current is None or len(prefix) > len(current[0]):
                best_for_key[key] = (prefix, idx)

    for key, (prefix, idx) in best_for_key.items():
        result[key] = (prefix, idx)
    return result


def unresolved_candidates(source: str, meta: MetaDict) -> list[UnresolvedCandidate]:
    """シリーズ自動判定で漏れた候補ペアを抽出する（A-6 / 機能追加候補.md）。

    既存の `detect_series_in_group` の閾値（SERIES_MIN_PREFIX_LEN=5 + 巻数パース成功）
    を意図的に緩めた debug 抽出。書き込み副作用なし。

    抽出ルール:
    - 既に `series_id` を持つ書籍はペアの両側で除外
    - reason='short_prefix': プレフィックス長 [3, 5) かつ巻数パース成功
    - reason='volume_parse_failed': プレフィックス長 >= 5 かつ巻数パース失敗

    Returns:
        score 降順で最大 SERIES_UNRESOLVED_MAX_CANDIDATES 件のリスト。
    """
    books = collect_books(source)
    groups = group_by_authors(books, meta)

    candidates: list[UnresolvedCandidate] = []
    for group in groups.values():
        # 既に series_id 割当済みの書籍を除外
        unassigned = [
            (path, name, title)
            for (path, name, title) in group
            if not meta.get(make_key(path, name), {}).get("series_id")
        ]
        n = len(unassigned)
        if n < 2:
            continue
        for i in range(n):
            for j in range(i + 1, n):
                path_i, name_i, title_i = unassigned[i]
                path_j, name_j, title_j = unassigned[j]
                prefix = common_prefix(title_i, title_j)
                pl = len(prefix)
                idx_i, idx_j = parse_pair_volume_indexes(
                    title_i[pl:], title_j[pl:]
                )
                parse_ok = idx_i is not None and idx_j is not None

                reason: UnresolvedReason | None = None
                if SERIES_CANDIDATE_MIN_PREFIX_LEN <= pl < SERIES_MIN_PREFIX_LEN and parse_ok:
                    reason = "short_prefix"
                elif pl >= SERIES_MIN_PREFIX_LEN and not parse_ok:
                    reason = "volume_parse_failed"
                if reason is None:
                    continue

                display_prefix = trim_prefix(prefix)
                if not display_prefix:
                    continue
                shorter_len = min(len(title_i), len(title_j))
                score = pl / shorter_len if shorter_len > 0 else 0.0
                candidates.append({
                    "reason": reason,
                    "score": round(score, 4),
                    "common_prefix": display_prefix,
                    "books": [
                        {"path": path_i, "name": name_i, "title": title_i},
                        {"path": path_j, "name": name_j, "title": title_j},
                    ],
                })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:SERIES_UNRESOLVED_MAX_CANDIDATES]


def collect_series_members(meta: MetaDict) -> dict[str, dict]:
    """meta から series_id ごとのメンバー情報（titles / max_index / series_title / authors_key）を集計して返す。"""
    series_members: dict[str, dict] = {}
    for key, entry in meta.items():
        sid = entry.get("series_id")
        if not sid:
            continue
        title = os.path.splitext(os.path.basename(key))[0]
        m = series_members.setdefault(sid, {
            "titles": [],
            "max_index": 0.0,
            "series_title": entry.get("series_title", ""),
            "authors_key": tuple(sorted({a.strip() for a in entry.get("authors", []) if a.strip()})),
        })
        m["titles"].append(title)
        m["max_index"] = max(m["max_index"], float(entry.get("series_index", 0)))
    return series_members
