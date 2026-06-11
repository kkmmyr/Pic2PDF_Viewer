"""書籍メタデータ管理ルーターパッケージ。3 サブルーターを /api プレフィックスで結合する。"""

from fastapi import APIRouter

from .admin import router as admin_router
from .core import router as core_router
from .novel import router as novel_router

router = APIRouter()
router.include_router(core_router)
router.include_router(novel_router)
router.include_router(admin_router)
