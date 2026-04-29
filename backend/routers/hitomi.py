"""hitomi.la 新着監視 API。

各エンドポイントの詳細は docs/03_詳細設計/hitomi新着監視設計書.md §6 を参照。
データは backend/data/hitomi/ 配下の JSON ファイル（個別の監視スクリプトが書き出す）。
"""
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.hitomi import state_store, watchlist
from tools import hitomi_monitor

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "hitomi"

# 同期 run-now の二重起動を防ぐ排他ロック
_run_lock = threading.Lock()


class AddWatchlistRequest(BaseModel):
    display_name: str
    language: str = "japanese"


# ---------------------------------------------------------------------------
# 新着一覧・既読化
# ---------------------------------------------------------------------------

@router.get("/hitomi/new-arrivals")
def get_new_arrivals() -> dict:
    """dismissed=false のアイテムを新着順で返す + ヘルス情報。"""
    state = state_store.load_state(DATA_DIR)
    arrivals = state_store.load_arrivals(DATA_DIR)
    items = [it for it in arrivals["items"] if not it.get("dismissed")]
    items.sort(key=lambda it: it.get("discovered_at", ""), reverse=True)
    return {
        "items": items,
        "last_run_at": state.get("last_run_at"),
        "last_run_status": state.get("last_run_status", "never"),
        "last_error": state.get("last_error"),
    }


@router.post("/hitomi/dismiss/{gallery_id}")
def post_dismiss(gallery_id: int) -> dict:
    if not state_store.dismiss(DATA_DIR, gallery_id):
        raise HTTPException(status_code=404, detail=f"Item not found: {gallery_id}")
    return {"message": "Dismissed", "id": gallery_id}


@router.post("/hitomi/dismiss-all")
def post_dismiss_all() -> dict:
    count = state_store.dismiss_all(DATA_DIR)
    return {"message": "All dismissed", "dismissed_count": count}


# ---------------------------------------------------------------------------
# 監視対象 CRUD
# ---------------------------------------------------------------------------

@router.get("/hitomi/watchlist")
def get_watchlist() -> dict:
    return {"artists": watchlist.load_watchlist(DATA_DIR)}


@router.post("/hitomi/watchlist")
def post_watchlist(req: AddWatchlistRequest) -> dict:
    try:
        entry = watchlist.add_artist(DATA_DIR, req.display_name, req.language)
    except watchlist.WatchlistError as e:
        msg = str(e)
        # NOZOMI に存在しない作者は 404、それ以外（重複・空文字）は 400
        if "not found on hitomi.la" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    return {"message": "Added", "normalized": entry["normalized"]}


@router.delete("/hitomi/watchlist/{normalized}")
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

@router.post("/hitomi/run-now")
def post_run_now() -> dict:
    """監視スクリプトを同期実行する。完了まで待つ。

    監視作者数 × 新着数に応じて数秒〜数十秒かかる。完了後は new_arrivals.json
    が更新されるので、クライアントは GET /api/hitomi/new-arrivals を再取得する。
    """
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="監視が既に実行中です")
    try:
        exit_code = hitomi_monitor.main(DATA_DIR)
        state = state_store.load_state(DATA_DIR)
        return {
            "exit_code": exit_code,
            "last_run_at": state.get("last_run_at"),
            "last_run_status": state.get("last_run_status", "never"),
            "last_error": state.get("last_error"),
        }
    finally:
        _run_lock.release()
