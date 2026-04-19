"""サークル名自動登録ジョブの管理。"""
import os
import threading
import time
from dataclasses import dataclass, field
from config import get_dirs_by_source
from services.author_resolver import resolve_author
from services.meta_store import get_lock, load_meta, save_meta, make_key

VALID_SOURCES = ("generated", "kindle", "novel")


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


def _has_real_author(meta: dict, key: str) -> bool:
    authors = meta.get(key, {}).get("authors", [])
    return bool(authors) and authors != ["作者不明"]


def run_auto_fill(source: str, overwrite: bool) -> None:
    """バックグラウンドでサークル名を順次解決して meta.json に保存する。"""
    state = get_auto_fill_state(source)
    try:
        pdf_root = get_dirs_by_source(source)["pdf"]

        all_pdfs: list[tuple[str, str]] = []
        if os.path.isdir(pdf_root):
            for root, _, files in os.walk(pdf_root):
                for f in sorted(files):
                    if f.lower().endswith(".pdf"):
                        rel = os.path.relpath(root, pdf_root)
                        rel_path = "" if rel == "." else rel.replace("\\", "/")
                        all_pdfs.append((rel_path, f))

        lock = get_lock(source)
        with lock:
            meta = load_meta(source)

        targets = all_pdfs if overwrite else [
            (p, f) for p, f in all_pdfs if not _has_real_author(meta, make_key(p, f))
        ]

        state.total = len(all_pdfs)
        state.skipped = len(all_pdfs) - len(targets)

        if not targets:
            state.status = "done"
            return

        for i, (rel_path, filename) in enumerate(targets):
            title = os.path.splitext(filename)[0]
            state.current = title

            author = resolve_author(title, source)

            with lock:
                meta = load_meta(source)
                meta[make_key(rel_path, filename)] = {"authors": [author]}
                save_meta(source, meta)

            state.results.append({"title": title, "author": author})
            state.done += 1

            # SearXNG の上流エンジンへの連続リクエストを避ける
            if i < len(targets) - 1:
                time.sleep(5.0)

        state.status = "done"
        state.current = ""

    except Exception as e:
        state.status = "error"
        state.error = str(e)
        state.current = ""


def start_auto_fill_job(source: str, overwrite: bool) -> None:
    """auto-fill ジョブをバックグラウンドスレッドで起動する。"""
    reset_auto_fill_state(source)
    thread = threading.Thread(target=run_auto_fill, args=(source, overwrite), daemon=True)
    thread.start()
