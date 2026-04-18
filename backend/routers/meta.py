"""
書籍メタデータ管理ルーター。

各ソースの meta.json に作者名などを保存・取得する。
保存先: backend/data/meta/{source}/meta.json
キー: "{path}/{filename}" の相対パス（path が空の場合は "{filename}"）
"""
import json
import os
import threading
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from config import DATA_DIR
from utils.path_utils import validate_safe_path, validate_safe_name

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
