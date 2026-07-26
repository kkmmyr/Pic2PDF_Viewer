"""hitomi.la 新着監視 API。

各エンドポイントの詳細は docs/design/詳細設計/機能別/hitomi新着監視設計書.md §6 を参照。
監視状態は hitomi/ 配下の JSON、検出作品と既読履歴は meta2.db に保存する。
"""

import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config import HITOMI_DATA_DIR as _hitomi_data_dir
from routers.api_schemas import (
    HitomiAddArtistResponse,
    HitomiArrivalsResponse,
    HitomiDismissAllResponse,
    HitomiDismissResponse,
    HitomiRemoveArtistResponse,
    HitomiRunNowResponse,
    HitomiWatchlistResponse,
)
from services.hitomi import arrival_store, nozomi, state_store, watchlist
from tools import hitomi_monitor
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

DATA_DIR = Path(_hitomi_data_dir)

# 同期 run-now の二重起動を防ぐ排他ロック
_run_lock = threading.Lock()


class AddWatchlistRequest(BaseModel):
    display_name: str
    language: str = "japanese"


# ---------------------------------------------------------------------------
# 新着一覧・既読化
# ---------------------------------------------------------------------------


@router.get("/hitomi/new-arrivals", response_model=HitomiArrivalsResponse)
def get_new_arrivals(
    status: Literal["unread", "read", "all"] = "unread",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=60, ge=1, le=200),
) -> dict:
    """指定既読状態の作品を新着順で返す + ヘルス情報。"""
    arrival_store.import_legacy_json(DATA_DIR)
    state = state_store.load_state(DATA_DIR)
    page = arrival_store.list_arrivals(status, offset, limit)
    return {
        **page,
        "status": status,
        "offset": offset,
        "limit": limit,
        "last_run_at": state.get("last_run_at"),
        "last_run_status": state.get("last_run_status", "never"),
        "last_error": state.get("last_error"),
    }


@router.post("/hitomi/dismiss/{gallery_id}", response_model=HitomiDismissResponse)
def post_dismiss(gallery_id: int) -> dict:
    arrival_store.import_legacy_json(DATA_DIR)
    if not arrival_store.dismiss(gallery_id):
        raise HTTPException(status_code=404, detail=f"Item not found: {gallery_id}")
    return {"message": "Dismissed", "id": gallery_id}


@router.post("/hitomi/dismiss-all", response_model=HitomiDismissAllResponse)
def post_dismiss_all() -> dict:
    arrival_store.import_legacy_json(DATA_DIR)
    count = arrival_store.dismiss_all()
    return {"message": "All dismissed", "dismissed_count": count}


# ---------------------------------------------------------------------------
# 監視対象 CRUD
# ---------------------------------------------------------------------------


@router.get("/hitomi/watchlist", response_model=HitomiWatchlistResponse)
def get_watchlist() -> dict:
    return {"artists": watchlist.load_watchlist(DATA_DIR)}


@router.post("/hitomi/watchlist", response_model=HitomiAddArtistResponse)
def post_watchlist(req: AddWatchlistRequest) -> dict:
    try:
        entry = watchlist.add_artist(DATA_DIR, req.display_name, req.language)
    except watchlist.WatchlistError as e:
        msg = str(e)
        # NOZOMI に存在しない作者は 404、それ以外（重複・空文字）は 400
        if "not found on hitomi.la" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e

    # 登録時点の最新 ID を state.json に書き込む。
    # これにより初回監視実行で「登録前から存在していた作品」が新着として出ない。
    key = f"{entry['normalized']}:{entry['language']}"
    try:
        ids = nozomi.fetch_nozomi_head(entry["normalized"], entry["language"], count=1)
        if ids:
            state = state_store.load_state(DATA_DIR)
            state.setdefault("artists", {})[key] = {"top_id": ids[0]}
            state_store.save_state(DATA_DIR, state)
    except nozomi.HitomiError as e:
        logger.warning("top_id 初期化スキップ（NOZOMI 取得失敗）: %s / %s", key, e)

    return {"message": "Added", "normalized": entry["normalized"]}


@router.delete("/hitomi/watchlist/{normalized}", response_model=HitomiRemoveArtistResponse)
def delete_watchlist(normalized: str, language: str = "japanese") -> dict:
    if not watchlist.remove_artist(DATA_DIR, normalized, language):
        raise HTTPException(status_code=404, detail=f"Not found: {normalized}")
    # 設計書 §6.6 に従い state.json の該当エントリも削除
    state = state_store.load_state(DATA_DIR)
    key = f"{normalized}:{language}"
    if state.get("artists", {}).pop(key, None) is not None:
        state_store.save_state(DATA_DIR, state)
    return {"message": "Removed"}


# ---------------------------------------------------------------------------
# 監視スクリプトの同期実行
# ---------------------------------------------------------------------------


@router.post("/hitomi/run-now", response_model=HitomiRunNowResponse)
def post_run_now(force: bool = False) -> dict:
    """監視スクリプトを同期実行する。完了まで待つ。

    既定では当日 0:00（ローカルタイム）以降にチェック済みの作者をスキップし、
    1 日 1 回までに頻度を抑える（0:00 を境にリセット）。`force=true` を渡すと
    全作者を強制再チェック。UI 連打や watchlist 編集ごとの全件再フェッチで
    hitomi.la に過剰アクセスしないための保険。Task Scheduler からの CLI
    直接実行はこの制限を受けない。
    """
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="監視が既に実行中です")
    try:
        threshold: datetime | None = None
        if not force:
            now_local = datetime.now().astimezone()
            threshold = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        exit_code = hitomi_monitor.main(DATA_DIR, threshold=threshold)
        state = state_store.load_state(DATA_DIR)
        return {
            "exit_code": exit_code,
            "last_run_at": state.get("last_run_at"),
            "last_run_status": state.get("last_run_status", "never"),
            "last_error": state.get("last_error"),
            "last_run_stats": state.get("last_run_stats"),
        }
    finally:
        _run_lock.release()
