from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from config import (
    CORS_ORIGINS,
    PDF_DIR, THUMBNAIL_DIR, IMAGES_DIR,
    KINDLE_PDF_DIR, KINDLE_THUMBNAIL_DIR, KINDLE_IMAGES_DIR,
    KINDLE_NOVEL_PDF_DIR, KINDLE_NOVEL_THUMBNAIL_DIR, KINDLE_NOVEL_IMAGES_DIR,
)
from exceptions import FileOperationError, OcrProcessError, AutoFillError
from routers import library, pdfs, ocr, meta
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

app.mount("/pdfs",        StaticFiles(directory=PDF_DIR),       name="pdfs")
app.mount("/thumbnails",  StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails")
app.mount("/images",      StaticFiles(directory=IMAGES_DIR),    name="images")

app.mount("/kindle/pdfs",        StaticFiles(directory=KINDLE_PDF_DIR),       name="kindle_pdfs")
app.mount("/kindle/thumbnails",  StaticFiles(directory=KINDLE_THUMBNAIL_DIR), name="kindle_thumbnails")
app.mount("/kindle/images",      StaticFiles(directory=KINDLE_IMAGES_DIR),    name="kindle_images")

app.mount("/kindle_novel/pdfs",        StaticFiles(directory=KINDLE_NOVEL_PDF_DIR),       name="kindle_novel_pdfs")
app.mount("/kindle_novel/thumbnails",  StaticFiles(directory=KINDLE_NOVEL_THUMBNAIL_DIR), name="kindle_novel_thumbnails")
app.mount("/kindle_novel/images",      StaticFiles(directory=KINDLE_NOVEL_IMAGES_DIR),    name="kindle_novel_images")

app.include_router(library.router, prefix="/api", tags=["library"])
app.include_router(pdfs.router,    prefix="/api", tags=["pdfs"])
app.include_router(ocr.router,     prefix="/api", tags=["ocr"])
app.include_router(meta.router,    prefix="/api", tags=["meta"])
