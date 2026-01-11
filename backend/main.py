from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from config import *
from routers import library, pdfs

app = FastAPI()

# CORS configuration
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount directories (using config constants)
# Generated (Default)
app.mount("/pdfs", StaticFiles(directory=PDF_DIR), name="pdfs")
app.mount("/thumbnails", StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails")
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

# Kindle
app.mount("/kindle/pdfs", StaticFiles(directory=KINDLE_PDF_DIR), name="kindle_pdfs")
app.mount("/kindle/thumbnails", StaticFiles(directory=KINDLE_THUMBNAIL_DIR), name="kindle_thumbnails")
app.mount("/kindle/images", StaticFiles(directory=KINDLE_IMAGES_DIR), name="kindle_images")

# Kindle Novel
app.mount("/kindle_novel/pdfs", StaticFiles(directory=KINDLE_NOVEL_PDF_DIR), name="kindle_novel_pdfs")
app.mount("/kindle_novel/thumbnails", StaticFiles(directory=KINDLE_NOVEL_THUMBNAIL_DIR), name="kindle_novel_thumbnails")
app.mount("/kindle_novel/images", StaticFiles(directory=KINDLE_NOVEL_IMAGES_DIR), name="kindle_novel_images")

# Include Routers
app.include_router(library.router, prefix="/api", tags=["library"])
app.include_router(pdfs.router, prefix="/api", tags=["pdfs"])

@app.get("/")
def read_root():
    return {"Hello": "World"}
