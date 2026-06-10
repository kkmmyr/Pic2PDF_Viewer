import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import (
    CORS_ORIGINS,
    FRONTEND_DIST_DIR,
    IMAGES_DIR,
    COMIC_IMAGES_DIR,
    KINDLE_NOVEL_IMAGES_DIR,
    KINDLE_NOVEL_THUMBNAIL_DIR,
    COMIC_PDF_DIR,
    COMIC_THUMBNAIL_DIR,
    PROJECT_ROOT,
    THUMBNAIL_DIR,
)
from exceptions import FileOperationError, OcrProcessError
from routers import (
    amazon_import,
    generate,
    genres,
    hitomi,
    library,
    meta,
    meta_db_backup,
    novel_build,
    novel_db,
    novel_discussion,
    novel_graph,
    ocr,
    pdfs,
    prefs,
    series,
    thumbnails,
)
from services.meta_db import init_db
from services.novel_db.job_queue import job_queue
from services.novel_db.migrations import upgrade_head
from utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """起動時に meta_db / novel_db の初期化・マイグレーションと job_queue worker を起動する。"""
    init_db()
    upgrade_head()
    await job_queue.start()
    try:
        yield
    finally:
        await job_queue.stop()


app = FastAPI(lifespan=lifespan)

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception at %s", request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ---------------------------------------------------------------------------
# 静的ファイルのマウント
# ---------------------------------------------------------------------------

app.mount("/thumbnails",  StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails")
app.mount("/images",      StaticFiles(directory=IMAGES_DIR),    name="images")

app.mount("/comic/pdfs",        StaticFiles(directory=COMIC_PDF_DIR),       name="comic_pdfs")
app.mount("/comic/thumbnails",  StaticFiles(directory=COMIC_THUMBNAIL_DIR), name="comic_thumbnails")
app.mount("/comic/images",      StaticFiles(directory=COMIC_IMAGES_DIR),    name="comic_images")

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
app.include_router(novel_db.router,         prefix="/api", tags=["novel_db"])
app.include_router(novel_discussion.router, prefix="/api", tags=["novel_discussion"])
app.include_router(novel_build.router,      prefix="/api", tags=["novel_build"])
app.include_router(amazon_import.router,    prefix="/api", tags=["amazon_import"])
app.include_router(meta_db_backup.router,  prefix="/api", tags=["meta_db_backup"])
app.include_router(novel_graph.router,     prefix="/api", tags=["novel_graph"])
app.include_router(prefs.router,           prefix="/api", tags=["prefs"])

# ---------------------------------------------------------------------------
# 設計ドキュメント HTML 配信（mkdocs ビルド成果物）
# ---------------------------------------------------------------------------
# `mkdocs build` の出力先は frontend/public/site/（Vite の publicDir 配下）。
# Vite dev/build 経由でも /site/ で配信されるが、リリース統合 (:8090) では
# 後方互換のため /docs-html にもマウントする。site/ が存在しない場合はスキップ。
# html=True により /docs-html/ で index.html を自動配信する。
# SPA catch-all より前に登録することで、/docs-html/* が優先的にこちらへ届く。

_DOCS_HTML_DIR = os.path.join(PROJECT_ROOT, "frontend", "public", "site")
if os.path.isdir(_DOCS_HTML_DIR):
    app.mount(
        "/docs-html",
        StaticFiles(directory=_DOCS_HTML_DIR, html=True),
        name="docs_html",
    )

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
