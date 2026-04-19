"""
書籍メタデータ管理ルーター。

各ソースの meta.json に作者名などを保存・取得する。
保存先: backend/data/meta/{source}/meta.json
キー: "{path}/{filename}" の相対パス（path が空の場合は "{filename}"）
"""
import json
import os
import threading
import time
from dataclasses import dataclass, field
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
from config import DATA_DIR, get_dirs_by_source
from utils.path_utils import validate_safe_path, validate_safe_name
from services.author_resolver import resolve_author

router = APIRouter()

# meta.json への書き込みをスレッドセーフにするロック（ソース別）
_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(source: str) -> threading.Lock:
    with _locks_lock:
        if source not in _locks:
            _locks[source] = threading.Lock()
        return _locks[source]


def _meta_path(source: str) -> str:
    """meta.json のフルパスを返す。"""
    meta_dir = os.path.join(DATA_DIR, "meta", source)
    os.makedirs(meta_dir, exist_ok=True)
    return os.path.join(meta_dir, "meta.json")


def _load_meta(source: str) -> dict:
    path = _meta_path(source)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_meta(source: str, data: dict) -> None:
    path = _meta_path(source)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _make_key(path: str, name: str) -> str:
    """メタデータのキーを生成する。"""
    return f"{path}/{name}" if path else name


# ---------------------------------------------------------------------------
# リクエスト/レスポンスモデル
# ---------------------------------------------------------------------------

class BookMetaEntry(BaseModel):
    authors: list[str]


class UpdateMetaRequest(BaseModel):
    """単一書籍または複数書籍へのメタデータ更新リクエスト。"""
    # 単一書籍の場合は names に 1 要素、複数の場合は複数要素を渡す
    path: str = ""
    names: list[str]          # ファイル名リスト（複数対応）
    authors: list[str]
    source: str = "generated"


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------

@router.get("/meta")
def get_meta(source: str = "generated") -> dict:
    """
    指定ソースの meta.json 全体を返す。
    レスポンス: { "key": { "authors": [...] }, ... }
    """
    if source not in ("generated", "kindle", "novel"):
        raise HTTPException(status_code=400, detail="Invalid source")
    return _load_meta(source)


@router.patch("/meta")
def update_meta(request: UpdateMetaRequest) -> dict:
    """
    1冊または複数冊の著者名を上書き保存する。
    names に複数ファイル名を渡すと一括更新できる。
    """
    if request.source not in ("generated", "kindle", "novel"):
        raise HTTPException(status_code=400, detail="Invalid source")

    validate_safe_path(request.path, param_name="path")
    for name in request.names:
        validate_safe_name(name, param_name="name")

    # authors の各要素を strip し、空文字を除去
    authors = [a.strip() for a in request.authors if a.strip()]

    lock = _get_lock(request.source)
    with lock:
        data = _load_meta(request.source)
        for name in request.names:
            key = _make_key(request.path, name)
            if authors:
                data[key] = {"authors": authors}
            else:
                # 著者が空になった場合はエントリごと削除
                data.pop(key, None)
        _save_meta(request.source, data)

    return {"message": "Updated", "updated_count": len(request.names)}


# ---------------------------------------------------------------------------
# 作者名自動登録ジョブ
# ---------------------------------------------------------------------------

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


# ソース別ジョブ状態（シングルトン）
_auto_fill_states: dict[str, AutoFillState] = {}
_auto_fill_states_lock = threading.Lock()


def _get_auto_fill_state(source: str) -> AutoFillState:
    with _auto_fill_states_lock:
        if source not in _auto_fill_states:
            _auto_fill_states[source] = AutoFillState()
        return _auto_fill_states[source]


def _run_auto_fill(source: str, overwrite: bool) -> None:
    """バックグラウンドでサークル名を順次解決して meta.json に保存する。"""
    state = _get_auto_fill_state(source)
    try:
        pdf_root = get_dirs_by_source(source)["pdf"]

        # PDFファイルを再帰的に収集
        all_pdfs: list[tuple[str, str]] = []
        if os.path.isdir(pdf_root):
            for root, _, files in os.walk(pdf_root):
                for f in sorted(files):
                    if f.lower().endswith(".pdf"):
                        rel = os.path.relpath(root, pdf_root)
                        rel_path = "" if rel == "." else rel.replace("\\", "/")
                        all_pdfs.append((rel_path, f))

        lock = _get_lock(source)
        with lock:
            meta = _load_meta(source)

        # overwrite=False: 登録済み（「作者不明」含む）をスキップ
        # overwrite=True:  全件処理（既存エントリを上書き）
        targets = all_pdfs if overwrite else [
            (p, f) for p, f in all_pdfs if _make_key(p, f) not in meta
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
                meta = _load_meta(source)
                meta[_make_key(rel_path, filename)] = {"authors": [author]}
                _save_meta(source, meta)

            state.results.append({"title": title, "author": author})
            state.done += 1

            # 最後の1件以外は待機（SearXNG への連続リクエストを避ける）
            if i < len(targets) - 1:
                time.sleep(1.0)

        state.status = "done"
        state.current = ""

    except Exception as e:
        state.status = "error"
        state.error = str(e)
        state.current = ""


@router.post("/meta/auto-fill")
def start_auto_fill(
    source: str = "generated",
    overwrite: bool = False,
) -> dict:
    """
    サークル名自動登録ジョブを開始する。
    - overwrite=False（デフォルト）: 登録済み（「作者不明」含む）はスキップ。
    - overwrite=True: 全件を上書き再処理。
    - 既にジョブが実行中の場合は 409 を返す。
    """
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")

    state = _get_auto_fill_state(source)
    if state.status == "running":
        raise HTTPException(status_code=409, detail="Auto-fill job is already running")

    # 状態をリセットして開始
    with _auto_fill_states_lock:
        _auto_fill_states[source] = AutoFillState(status="running")

    thread = threading.Thread(target=_run_auto_fill, args=(source, overwrite), daemon=True)
    thread.start()

    return {"started": True, "source": source, "overwrite": overwrite}


@router.get("/meta/auto-fill/status")
def get_auto_fill_status(source: str = "generated") -> dict:
    """作者名自動登録ジョブの進捗を返す。"""
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail="Invalid source")

    state = _get_auto_fill_state(source)
    return {
        "status": state.status,
        "total": state.total,
        "done": state.done,
        "skipped": state.skipped,
        "current": state.current,
        "results": state.results,
        "error": state.error,
    }
