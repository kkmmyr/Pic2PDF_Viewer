"""シリーズ自動グループ化ジョブ実行サービス。

判定ロジックは `services/series_detector.py` を参照。本モジュールは
`SeriesResolveState` 状態管理、Gemma 補助、バックグラウンドスレッド起動を担当する。

Phase 1: ルールベース判定（detector に委譲）。
Phase 2: `use_gemma=True` 指定時、ルール判定後に同作者でシリーズ未割当の
書籍を Gemma に問い合わせて既存シリーズに追加するかを判定する。
"""
import threading
from dataclasses import dataclass

from services.gemma_client import import_ollama_client
from services.job_state import JobStateManager
from services.meta_store import MetaDict, load_meta, make_key, update_meta_locked
from services.series_detector import (
    collect_books,
    collect_series_members,
    detect_series_in_group,
    group_by_authors,
    stable_series_id,
)
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SeriesResolveState:
    status: str = "idle"   # idle | running | done | error
    total: int = 0
    done: int = 0
    created: int = 0
    current: str = ""
    error: str = ""


_manager: JobStateManager[SeriesResolveState] = JobStateManager(
    idle_factory=SeriesResolveState,
    running_factory=lambda: SeriesResolveState(status="running"),
)


def get_state(source: str) -> SeriesResolveState:
    return _manager.get(source)


def reset_state(source: str) -> None:
    _manager.reset(source)


# ---------------------------------------------------------------------------
# Gemma 補助（Phase 2）
# ---------------------------------------------------------------------------

def _ask_gemma_is_same_series(
    call_ollama, reference_titles: list[str], candidate_title: str
) -> bool:
    """Gemma に「candidate_title は reference_titles と同じシリーズか？」を問う。

    応答が "YES" で始まれば True。タイムアウト・例外時は False（黙って除外）。
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


def _assign_book_to_series(
    source: str,
    target_key: str,
    sid: str,
    info: dict,
    created_series: set[str],
    state: SeriesResolveState,
) -> None:
    """未割当書籍を既存シリーズに追加し meta を更新する（既存 max_index + 1 で採番）。"""
    info["max_index"] = float(int(info["max_index"]) + 1)
    next_idx = info["max_index"]
    series_title = info["series_title"]

    def _apply(data: MetaDict, k=target_key, sid_=sid, idx=next_idx, st=series_title) -> None:
        existing = dict(data.get(k, {}))
        existing["series_id"] = sid_
        existing["series_title"] = st
        existing["series_index"] = idx
        data[k] = existing

    update_meta_locked(source, _apply)
    created_series.add(sid)
    state.created = len(created_series)


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

    meta = load_meta(source)
    series_members = collect_series_members(meta)

    for ak, group in groups.items():
        unassigned = [
            (rel_path, fname, title)
            for (rel_path, fname, title) in group
            if not meta.get(make_key(rel_path, fname), {}).get("series_id")
        ]
        if not unassigned:
            continue

        relevant_series = {
            sid: m for sid, m in series_members.items() if m["authors_key"] == ak
        }
        if not relevant_series:
            continue

        for (rel_path, fname, title) in unassigned:
            state.current = title
            for sid, info in relevant_series.items():
                if not _ask_gemma_is_same_series(call_ollama, info["titles"], title):
                    continue
                info["titles"].append(title)
                _assign_book_to_series(source, make_key(rel_path, fname), sid, info, created_series, state)
                break  # 1 つのシリーズにマッチしたら以降は試さない


def run_resolve(source: str, use_gemma: bool = False) -> None:
    """対象ソースのシリーズ判定を実行し、`meta.json` に書き戻す。

    Args:
        source: `generated` / `kindle` / `novel`
        use_gemma: True の場合、ルール判定後に Gemma で曖昧ケースを再評価する。
    """
    state = get_state(source)
    try:
        books = collect_books(source)
        state.total = len(books)

        # スナップショットを取って判定（書き込みは更新時に都度ロック取得）
        meta_snapshot = load_meta(source)
        groups = group_by_authors(books, meta_snapshot)

        # 既存の series_* を全部一旦クリア（再ラベルするため）
        def _clear_series(data: MetaDict) -> None:
            for entry in data.values():
                entry.pop("series_id", None)
                entry.pop("series_title", None)
                entry.pop("series_index", None)
        update_meta_locked(source, _clear_series)

        created_series: set[str] = set()
        per_group_done = 0
        for ak, group in groups.items():
            detected = detect_series_in_group(group)
            if not detected:
                per_group_done += len(group)
                state.done = per_group_done
                continue

            # まとめて 1 回のロックで書き込む
            def _apply(data: MetaDict, det=detected, akv=ak) -> None:
                for key, (prefix, idx) in det.items():
                    sid = stable_series_id(prefix, akv)
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
