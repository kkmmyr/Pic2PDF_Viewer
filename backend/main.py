import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from config import (
    CORS_ORIGINS,
    THUMBNAIL_DIR, IMAGES_DIR,
    KINDLE_PDF_DIR, KINDLE_THUMBNAIL_DIR, KINDLE_IMAGES_DIR,
    KINDLE_NOVEL_PDF_DIR, KINDLE_NOVEL_THUMBNAIL_DIR, KINDLE_NOVEL_IMAGES_DIR,
    FRONTEND_DIST_DIR,
)
from exceptions import FileOperationError, OcrProcessError, AutoFillError
from routers import library, pdfs, generate, ocr, meta, thumbnails, series, hitomi, genres
from utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 例外ハンドラ
# ---------------------------------------------------------------------------

@app.exception_handler(FileOperationError)
async def file_operation_error_handler(request: Request, exc: FileOperationError):
    logger.exception("FileOperationError at %s: %s", request.url, exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(OcrProcessError)
async def ocr_process_error_handler(request: Request, exc: OcrProcessError):
    logger.exception("OcrProcessError at %s: %s", request.url, exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(AutoFillError)
async def auto_fill_error_handler(request: Request, exc: AutoFillError):
    logger.exception("AutoFillError at %s: %s", request.url, exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception at %s", request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ---------------------------------------------------------------------------
# 静的ファイルのマウント
# ---------------------------------------------------------------------------

app.mount("/thumbnails",  StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails")
app.mount("/images",      StaticFiles(directory=IMAGES_DIR),    name="images")

app.mount("/kindle/pdfs",        StaticFiles(directory=KINDLE_PDF_DIR),       name="kindle_pdfs")
app.mount("/kindle/thumbnails",  StaticFiles(directory=KINDLE_THUMBNAIL_DIR), name="kindle_thumbnails")
app.mount("/kindle/images",      StaticFiles(directory=KINDLE_IMAGES_DIR),    name="kindle_images")

app.mount("/kindle_novel/pdfs",        StaticFiles(directory=KINDLE_NOVEL_PDF_DIR),       name="kindle_novel_pdfs")
app.mount("/kindle_novel/thumbnails",  StaticFiles(directory=KINDLE_NOVEL_THUMBNAIL_DIR), name="kindle_novel_thumbnails")
app.mount("/kindle_novel/images",      StaticFiles(directory=KINDLE_NOVEL_IMAGES_DIR),    name="kindle_novel_images")

app.include_router(library.router,    prefix="/api", tags=["library"])
app.include_router(pdfs.router,       prefix="/api", tags=["pdfs"])
app.include_router(generate.router,   prefix="/api", tags=["generate"])
app.include_router(thumbnails.router, prefix="/api", tags=["thumbnails"])
app.include_router(ocr.router,        prefix="/api", tags=["ocr"])
app.include_router(meta.router,       prefix="/api", tags=["meta"])
app.include_router(series.router,     prefix="/api", tags=["series"])
app.include_router(hitomi.router,     prefix="/api", tags=["hitomi"])
app.include_router(genres.router,     prefix="/api", tags=["genres"])

# ---------------------------------------------------------------------------
# フロントエンド SPA 配信（リリースモード）
# ---------------------------------------------------------------------------
# frontend/dist/ が存在する場合のみ有効化。dev モードでは無視される。
# SPA catch-all は最後に登録し、/api・/pdfs 等の既存マウントが優先されるようにする。

if os.path.isdir(FRONTEND_DIST_DIR):
    _ASSETS_DIR = os.path.join(FRONTEND_DIST_DIR, "assets")
    if os.path.isdir(_ASSETS_DIR):
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="frontend_assets")

    _INDEX_HTML = os.path.join(FRONTEND_DIST_DIR, "index.html")

    @app.get("/")
    async def _serve_index():
        return FileResponse(_INDEX_HTML)

    @app.get("/{full_path:path}")
    async def _serve_spa(full_path: str):
        # API ルートは catch-all から除外（404 のまま）
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        # dist/ 配下に実ファイルがあればそれを返す（vite.svg, favicon.ico 等）
        candidate = os.path.join(FRONTEND_DIST_DIR, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        # それ以外は SPA ルーティング用に index.html を返す
        return FileResponse(_INDEX_HTML)
