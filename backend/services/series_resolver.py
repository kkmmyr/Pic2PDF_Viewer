"""シリーズ自動グループ化サービス。

「同じ作者 + タイトル前方一致 + 残部分が巻数パターン」を満たす書籍ペアを
シリーズとしてグループ化し、`meta.json` に `series_id` / `series_title` /
`series_index` を書き戻す。

Phase 1: ルールベース。
Phase 2: `use_gemma=True` 指定時、ルール判定後に同作者でシリーズ未割当の
書籍を Gemma に問い合わせて既存シリーズに追加するかを判定する。
"""
import hashlib
import os
import threading
from dataclasses import dataclass, field

from config import get_dirs_by_source
from services.gemma_client import import_ollama_client
from services.meta_store import MetaDict, load_meta, make_key, update_meta_locked
from services.volume_parser import parse_pair_volume_indexes
from utils.file_utils import is_pdf_file
from utils.logger import get_logger

logger = get_logger(__name__)

VALID_SOURCES = ("generated", "kindle", "novel")
SERIES_MIN_PREFIX_LEN = 5


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


# ---------------------------------------------------------------------------
# Gemma 補助（Phase 2）
# ---------------------------------------------------------------------------

def _ask_gemma_is_same_series(
    call_ollama, reference_titles: list[str], candidate_title: str
) -> bool:
    """Gemma に「candidate_title は reference_titles と同じシリーズか？」を問う。

    `call_ollama` は `_ensure_ollama_client()` の戻り値。応答が "YES" で
    始まれば True を返す。タイムアウト・例外時は False（黙って除外）。
    """
    refs = "\n".join(f"- {t}" for t in reference_titles[:5])
    prompt = (
        f"以下のタイトルは同じシリーズの書籍ですか？YES または NO のいずれかだけで答えてください。\n\n"
        f"シリーズの代表タイトル:\n{refs}\n\n"
        f"判定対象:\n- {candidate_title}\n\n"
        f"YES または NO:"
    )
    try:
        response = call_ollama(prompt, source="series_resolver")
        return str(response).strip().upper().startswith("YES")
    except Exception as e:
        logger.warning("Gemma series check failed for %r: %s", candidate_title, e)
        return False


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
            prefix = _common_prefix(ti, tj)
            if len(prefix) < SERIES_MIN_PREFIX_LEN:
                continue
            # 「巻数なし＝1巻」ルール込みで巻数解析
            idx_i, idx_j = parse_pair_volume_indexes(ti[len(prefix):], tj[len(prefix):])
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
    best_for_key: dict[str, tuple[str, float]] = {}
    for prefix, members in prefix_to_members.items():
        for key, _name, idx in members:
            current = best_for_key.get(key)
            if current is None or len(prefix) > len(current[0]):
                best_for_key[key] = (prefix, idx)

    for key, (prefix, idx) in best_for_key.items():
        result[key] = (prefix, idx)
    return result


def _augment_with_gemma(
    source: str,
    groups: dict[tuple[str, ...], list[tuple[str, str, str]]],
    created_series: set[str],
    state: SeriesResolveState,
) -> None:
    """ルール判定後に Gemma で曖昧ケースを再評価する。

    各シリーズ（既に series_id が割り当てられたメンバー集合）に対し、
    同作者でシリーズ未割当の書籍を Gemma に問い合わせる。
    """
    call_ollama = import_ollama_client()
    if call_ollama is None:
        logger.warning("Gemma client unavailable; skipping use_gemma phase")
        return

    # 最新の meta を読み直して、ルール判定で割り当てられたシリーズ情報を取得
    meta = load_meta(source)

    # series_id ごとのメンバー（タイトル・キー・現在の最大 index）を集計
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

    # 各作者グループから「シリーズ未割当」の書籍を抽出
    for authors_key, group in groups.items():
        unassigned = [
            (rel_path, fname, title)
            for (rel_path, fname, title) in group
            if not meta.get(make_key(rel_path, fname), {}).get("series_id")
        ]
        if not unassigned:
            continue

        # この作者の既存シリーズだけを問い合わせ対象にする
        relevant_series = {
            sid: m for sid, m in series_members.items() if m["authors_key"] == authors_key
        }
        if not relevant_series:
            continue

        for (rel_path, fname, title) in unassigned:
            state.current = title
            for sid, info in relevant_series.items():
                if not _ask_gemma_is_same_series(call_ollama, info["titles"], title):
                    continue

                # シリーズに追加（既存 max_index + 1、整数巻として割り当て）
                info["max_index"] = float(int(info["max_index"]) + 1)
                next_idx = info["max_index"]
                info["titles"].append(title)
                series_title = info["series_title"]
                target_key = make_key(rel_path, fname)

                def _apply(data: MetaDict, k=target_key, sid_=sid, idx=next_idx, st=series_title) -> None:
                    existing = dict(data.get(k, {}))
                    existing["series_id"] = sid_
                    existing["series_title"] = st
                    existing["series_index"] = idx
                    data[k] = existing
                update_meta_locked(source, _apply)

                created_series.add(sid)
                state.created = len(created_series)
                break  # 1 つのシリーズにマッチしたら以降は試さない


def run_resolve(source: str, use_gemma: bool = False) -> None:
    """対象ソースのシリーズ判定を実行し、`meta.json` に書き戻す。

    Args:
        source: `generated` / `kindle` / `novel`
        use_gemma: True の場合、ルール判定後に Gemma で曖昧ケースを再評価する。
    """
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

        # Phase 2: Gemma 補助
        if use_gemma:
            _augment_with_gemma(source, groups, created_series, state)

        # books に作者なしの書籍が含まれている場合は per_group_done < total になる。
        # 最終的に done = total に揃える。
        state.done = state.total
        state.status = "done"
        state.current = ""
    except Exception as e:
        state.status = "error"
        state.error = str(e)
        state.current = ""


def start_resolve_job(source: str, use_gemma: bool = False) -> None:
    """シリーズ判定ジョブをバックグラウンドスレッドで起動する。"""
    reset_state(source)
    thread = threading.Thread(target=run_resolve, args=(source, use_gemma), daemon=True)
    thread.start()
