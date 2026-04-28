"""シリーズ自動グループ化サービス。

「同じ作者 + タイトル前方一致 + 残部分が巻数パターン」を満たす書籍ペアを
シリーズとしてグループ化し、`meta.json` に `series_id` / `series_title` /
`series_index` を書き戻す。

Phase 1: ルールベースのみ。Phase 2 で Gemma 補助を追加予定（現時点では未使用）。
"""
import hashlib
import os
import re
import threading
from dataclasses import dataclass, field

from config import get_dirs_by_source
from services.meta_store import MetaDict, load_meta, make_key, update_meta_locked
from utils.file_utils import is_pdf_file

VALID_SOURCES = ("generated", "kindle", "novel")
SERIES_MIN_PREFIX_LEN = 5

# 巻数パターン（プレフィックス除去後のサフィックスに対して使う）
_KANJI_NUMS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_RE_NUM    = re.compile(r"^\s*[第]?\s*(\d+)\s*[巻]?\s*$")
_RE_VOL    = re.compile(r"^\s*[vV][oO][lL]\.?\s*(\d+)\s*$")
_RE_PAREN  = re.compile(r"^\s*[(（]([上中下前後]+)[)）]\s*$")
_RE_KANJI  = re.compile(r"^\s*第?([一二三四五六七八九十百]+)巻?\s*$")
_PAREN_INDEX = {"上": 1, "中": 2, "下": 3, "前": 1, "後": 2}


@dataclass
class SeriesResolveState:
    status: str = "idle"   # idle | running | done | error
    total: int = 0
    done: int = 0
    created: int = 0
    current: str = ""
    error: str = ""


_states: dict[str, SeriesResolveState] = {}
_states_lock = threading.Lock()


def get_state(source: str) -> SeriesResolveState:
    with _states_lock:
        if source not in _states:
            _states[source] = SeriesResolveState()
        return _states[source]


def reset_state(source: str) -> None:
    with _states_lock:
        _states[source] = SeriesResolveState(status="running")


def _parse_volume_index(suffix: str) -> int | None:
    """サフィックスを巻数（1始まり）に正規化する。マッチしなければ None。"""
    s = suffix.strip()
    if not s:
        return None
    if m := _RE_NUM.match(s):
        return int(m.group(1))
    if m := _RE_VOL.match(s):
        return int(m.group(1))
    if m := _RE_PAREN.match(s):
        kana = m.group(1)
        # 単独文字のみ対応（「上下」のような並びは扱わない）
        if len(kana) == 1 and kana in _PAREN_INDEX:
            return _PAREN_INDEX[kana]
        return None
    if m := _RE_KANJI.match(s):
        kanji = m.group(1)
        # 単純な漢数字のみ対応（一〜十）
        if len(kanji) == 1 and kanji in _KANJI_NUMS:
            return _KANJI_NUMS[kanji]
        # 二桁: 「十一」「十二」… は省略（一〜十のみ対応）
        return None
    return None


def _common_prefix(a: str, b: str) -> str:
    """2 文字列の共通前方プレフィックスを返す。"""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return a[:i]
    return a[:n]


def _authors_key(authors: list[str]) -> tuple[str, ...]:
    """作者リストを順序非依存の集合キーに変換する。"""
    return tuple(sorted({a.strip() for a in authors if a.strip()}))


def _stable_series_id(prefix: str, authors_key: tuple[str, ...]) -> str:
    """共通プレフィックス + 作者集合から安定したシリーズ ID を作る。"""
    raw = prefix + "\x00" + "\x00".join(authors_key)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _trim_prefix(prefix: str) -> str:
    """シリーズ表示名として使うため、末尾の余分な空白・記号を除去する。"""
    return prefix.rstrip(" 　-_:：・")


def _collect_books(source: str) -> list[tuple[str, str, str]]:
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


def _group_by_authors(
    books: list[tuple[str, str, str]],
    meta: MetaDict,
) -> dict[tuple[str, ...], list[tuple[str, str, str]]]:
    """書籍を作者集合キーごとにグループ化する。作者なしは除外。"""
    groups: dict[tuple[str, ...], list[tuple[str, str, str]]] = {}
    for rel_path, filename, title in books:
        key = make_key(rel_path, filename)
        authors = meta.get(key, {}).get("authors") or []
        akey = _authors_key(authors)
        if not akey:
            continue
        groups.setdefault(akey, []).append((rel_path, filename, title))
    return groups


def _detect_series_in_group(
    group: list[tuple[str, str, str]],
) -> dict[str, tuple[str, int]]:
    """1 つの作者グループ内でシリーズ判定する。

    Returns:
        `{ make_key(rel_path, filename): (series_title, series_index) }` のマップ。
    """
    result: dict[str, tuple[str, int]] = {}
    n = len(group)
    if n < 2:
        return result

    # 同じプレフィックスを共有するメンバーを集める。プレフィックスは
    # 「ペアごとに最大共通プレフィックス」を取ってから巻数判定が成立する組のみ採用。
    # 効率より分かりやすさ優先で全ペア O(n^2)。書籍数が数千以下なら問題ない。
    prefix_to_members: dict[str, list[tuple[str, str, int]]] = {}
    for i in range(n):
        for j in range(i + 1, n):
            ti, tj = group[i][2], group[j][2]
            prefix = _common_prefix(ti, tj)
            if len(prefix) < SERIES_MIN_PREFIX_LEN:
                continue
            idx_i = _parse_volume_index(ti[len(prefix):])
            idx_j = _parse_volume_index(tj[len(prefix):])
            if idx_i is None or idx_j is None:
                continue
            display = _trim_prefix(prefix)
            if not display:
                continue
            members = prefix_to_members.setdefault(display, [])
            for path, name, idx in [(group[i][0], group[i][1], idx_i), (group[j][0], group[j][1], idx_j)]:
                key = make_key(path, name)
                if not any(k == key for k, _, _ in members):
                    members.append((key, name, idx))

    # 同じ書籍が複数グループに属した場合は「最も長いプレフィックス」を採用
    best_for_key: dict[str, tuple[str, int]] = {}
    for prefix, members in prefix_to_members.items():
        for key, _name, idx in members:
            current = best_for_key.get(key)
            if current is None or len(prefix) > len(current[0]):
                best_for_key[key] = (prefix, idx)

    for key, (prefix, idx) in best_for_key.items():
        result[key] = (prefix, idx)
    return result


def run_resolve(source: str) -> None:
    """対象ソースのシリーズ判定を実行し、`meta.json` に書き戻す。"""
    state = get_state(source)
    try:
        books = _collect_books(source)
        state.total = len(books)

        # スナップショットを取って判定（書き込みは更新時に都度ロック取得）
        meta_snapshot = load_meta(source)
        groups = _group_by_authors(books, meta_snapshot)

        # 既存の series_* を全部一旦クリア（再ラベルするため）
        def _clear_series(data: MetaDict) -> None:
            for entry in data.values():
                entry.pop("series_id", None)
                entry.pop("series_title", None)
                entry.pop("series_index", None)
        update_meta_locked(source, _clear_series)

        created_series: set[str] = set()
        per_group_done = 0
        for authors_key, group in groups.items():
            detected = _detect_series_in_group(group)
            if not detected:
                per_group_done += len(group)
                state.done = per_group_done
                continue

            # まとめて 1 回のロックで書き込む
            def _apply(data: MetaDict, det=detected, ak=authors_key) -> None:
                for key, (prefix, idx) in det.items():
                    sid = _stable_series_id(prefix, ak)
                    existing = dict(data.get(key, {}))
                    existing["series_id"] = sid
                    existing["series_title"] = prefix
                    existing["series_index"] = idx
                    data[key] = existing
                    created_series.add(sid)
            update_meta_locked(source, _apply)

            per_group_done += len(group)
            state.done = per_group_done
            state.created = len(created_series)
            # 1 グループあたりの最初の書籍タイトルを current に
            state.current = group[0][2] if group else ""

        # books に作者なしの書籍が含まれている場合は per_group_done < total になる。
        # 最終的に done = total に揃える。
        state.done = state.total
        state.status = "done"
        state.current = ""
    except Exception as e:
        state.status = "error"
        state.error = str(e)
        state.current = ""


def start_resolve_job(source: str) -> None:
    """シリーズ判定ジョブをバックグラウンドスレッドで起動する。"""
    reset_state(source)
    thread = threading.Thread(target=run_resolve, args=(source,), daemon=True)
    thread.start()
