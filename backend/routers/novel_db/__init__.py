"""novel_db ルーターパッケージ。6 サブルーターを /novel_db プレフィックスで結合する。"""
from fastapi import APIRouter

from .character import router as character_router
from .chat import router as chat_router
from .lib import router as lib_router
from .qa import router as qa_router
from .rebuild import router as rebuild_router
from .search import router as search_router

router = APIRouter()
# character_router を先に登録して /books/{name:path}/characters が
# lib_router の /books/{name:path} に飲み込まれないようにする
router.include_router(character_router, prefix="/novel_db")
router.include_router(lib_router, prefix="/novel_db")
router.include_router(rebuild_router, prefix="/novel_db")
router.include_router(search_router, prefix="/novel_db")
router.include_router(qa_router, prefix="/novel_db")
router.include_router(chat_router, prefix="/novel_db")
