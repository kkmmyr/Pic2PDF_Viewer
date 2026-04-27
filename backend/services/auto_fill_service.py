"""サークル名自動登録ジョブの管理。"""
import os
import threading
import time
from dataclasses import dataclass, field
from config import get_dirs_by_source
from services.author_resolver import resolve_author
from services.meta_store import MetaDict, get_lock, load_meta, make_key, update_meta_locked
from utils.file_utils import is_pdf_file

VALID_SOURCES = ("generated", "kindle", "novel")
VALID_MODES = ("missing_only", "unknown_only", "overwrite_all")
AUTOFILL_REQUEST_DELAY_SEC = 5.0


@dataclass
class AutoFillState:
    status: str = "idle"   # idle | running | done | error
    total: int = 0
    done: int = 0
    skipped: int = 0
    current: str = ""
    results: list = field(default_factory=list)
    error: str = ""


_auto_fill_states: dict[str, AutoFillState] = {}
_auto_fill_states_lock = threading.Lock()


def get_auto_fill_state(source: str) -> AutoFillState:
    with _auto_fill_states_lock:
        if source not in _auto_fill_states:
            _auto_fill_states[source] = AutoFillState()
        return _auto_fill_states[source]


def reset_auto_fill_state(source: str) -> None:
    with _auto_fill_states_lock:
        _auto_fill_states[source] = AutoFillState(status="running")


def _is_missing(meta: MetaDict, key: str) -> bool:
    """作者名エントリが存在しない（完全未登録）。"""
    return key not in meta or not meta[key].get("authors")


def _is_unknown(meta: MetaDict, key: str) -> bool:
    """作者名が「作者不明」。"""
    return meta.get(key, {}).get("authors") == ["作者不明"]


def run_auto_fill(source: str, mode: str) -> None:
    """バックグラウンドでサークル名を順次解決して meta.json に保存する。

    mode:
        missing_only  — 作者名エントリが存在しない書籍のみ
        unknown_only  — 「作者不明」の書籍のみ
        overwrite_all — 全件を上書き
    """
    state = get_auto_fill_state(source)
    try:
        pdf_root = get_dirs_by_source(source)["pdf"]

        all_pdfs: list[tuple[str, str]] = []
        if os.path.isdir(pdf_root):
            for root, _, files in os.walk(pdf_root):
                for f in sorted(files):
                    if is_pdf_file(f):
                        rel = os.path.relpath(root, pdf_root)
                        rel_path = "" if rel == "." else rel.replace("\\", "/")
                        all_pdfs.append((rel_path, f))

        lock = get_lock(source)
        with lock:
            meta = load_meta(source)

        if mode == "overwrite_all":
            targets = all_pdfs
        elif mode == "missing_only":
            targets = [(p, f) for p, f in all_pdfs if _is_missing(meta, make_key(p, f))]
        else:  # unknown_only (default)
            targets = [
                (p, f) for p, f in all_pdfs
                if _is_missing(meta, k := make_key(p, f)) or _is_unknown(meta, k)
            ]

        state.total = len(targets)
        state.skipped = len(all_pdfs) - len(targets)

        if not targets:
            state.status = "done"
            return

        for i, (rel_path, filename) in enumerate(targets):
            title = os.path.splitext(filename)[0]
            state.current = title

            author = resolve_author(title, source)
            key = make_key(rel_path, filename)

            # 既存の view_count / last_viewed_at を保持して authors のみ更新する
            def _apply(m, k=key, a=author):
                existing = m.get(k, {})
                m[k] = {**existing, "authors": [a]}
            update_meta_locked(source, _apply)

            state.results.append({"title": title, "author": author})
            state.done += 1

            if i < len(targets) - 1:
                time.sleep(AUTOFILL_REQUEST_DELAY_SEC)

        state.status = "done"
        state.current = ""

    except Exception as e:
        state.status = "error"
        state.error = str(e)
        state.current = ""


def start_auto_fill_job(source: str, mode: str) -> None:
    """auto-fill ジョブをバックグラウンドスレッドで起動する。"""
    reset_auto_fill_state(source)
    thread = threading.Thread(target=run_auto_fill, args=(source, mode), daemon=True)
    thread.start()
