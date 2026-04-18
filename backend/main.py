from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from config import (
    CORS_ORIGINS,
    PDF_DIR, THUMBNAIL_DIR, IMAGES_DIR,
    KINDLE_PDF_DIR, KINDLE_THUMBNAIL_DIR, KINDLE_IMAGES_DIR,
    KINDLE_NOVEL_PDF_DIR, KINDLE_NOVEL_THUMBNAIL_DIR, KINDLE_NOVEL_IMAGES_DIR,
)
from routers import library, pdfs, ocr, meta

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静的ファイルのマウント
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
