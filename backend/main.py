from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import fitz  # PyMuPDF
from PIL import Image
from services.pdf_generator import scan_and_generate

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

# Base Data Directory
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Ensure pdfs directory exists
PDF_DIR = os.path.join(DATA_DIR, "pdfs")
os.makedirs(PDF_DIR, exist_ok=True)

# Ensure thumbnails directory exists
THUMBNAIL_DIR = os.path.join(DATA_DIR, "thumbnails")
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

# Ensure images directory exists
IMAGES_DIR = os.path.join(DATA_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

# Ensure complete directory exists
COMPLETE_DIR = os.path.join(os.path.dirname(__file__), "complete")
os.makedirs(COMPLETE_DIR, exist_ok=True)

# Mount directories
app.mount("/pdfs", StaticFiles(directory=PDF_DIR), name="pdfs")
app.mount("/thumbnails", StaticFiles(directory=THUMBNAIL_DIR), name="thumbnails")
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

# Global state to track progress
current_processing_item = None

class GenerateRequest(BaseModel):
    source_dir: str

def generate_thumbnail_task(pdf_path: str, thumbnail_path: str):
    """
    Background task to generate a thumbnail from the first page of a PDF.
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
        
        doc = fitz.open(pdf_path)
        if len(doc) > 0:
            page = doc.load_page(0)  # first page
            pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5)) # Scale down to 50%
            
            # Save as JPEG
            pix.save(thumbnail_path)
            print(f"Generated thumbnail: {thumbnail_path}")
        doc.close()
    except Exception as e:
        print(f"Failed to generate thumbnail for {pdf_path}: {e}")

@app.post("/api/generate")
def generate_pdfs(request: GenerateRequest):
    global current_processing_item
    if not os.path.isdir(request.source_dir):
        raise HTTPException(status_code=400, detail="Invalid directory path")
    
    def progress_callback(item_name):
        global current_processing_item
        current_processing_item = item_name
        print(f"Processing: {item_name}")

    try:
        current_processing_item = "Starting..."
        # Pass THUMBNAIL_DIR and IMAGES_DIR to the generator
        generated = scan_and_generate(request.source_dir, PDF_DIR, THUMBNAIL_DIR, IMAGES_DIR, COMPLETE_DIR, progress_callback)
        current_processing_item = None
        return {"message": "Generation complete", "files": generated}
    except Exception as e:
        current_processing_item = None
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status")
def get_status(source_dir: str):
    if not os.path.isdir(source_dir):
        return {"items": []}

    items_status = []
    
    # 1. Scan source directory for candidates
    for root, dirs, files in os.walk(source_dir):
        # Check for folders with WebP
        webp_files = [f for f in files if f.lower().endswith('.webp')]
        if webp_files:
            folder_name = os.path.basename(root)
            if root == source_dir:
                folder_name = os.path.basename(source_dir)
            
            status = "not_started"
            pdf_path = os.path.join(PDF_DIR, f"{folder_name}.pdf")
            
            if current_processing_item == folder_name:
                status = "in_progress"
            elif os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                status = "completed"
            
            items_status.append({"name": folder_name, "type": "folder", "status": status})

        # Check for ZIP files
        zip_files = [f for f in files if f.lower().endswith('.zip')]
        for zip_file in zip_files:
            item_name = os.path.splitext(zip_file)[0]
            
            status = "not_started"
            pdf_path = os.path.join(PDF_DIR, f"{item_name}.pdf")
            
            if current_processing_item == item_name:
                status = "in_progress"
            elif os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                status = "completed"
                
            items_status.append({"name": item_name, "type": "zip", "status": status})
            
    return {"items": items_status}

@app.get("/api/pdfs")
def list_pdfs(background_tasks: BackgroundTasks, path: str = ""):
    # Prevent directory traversal
    if ".." in path or path.startswith("/") or path.startswith("\\"):
         raise HTTPException(status_code=400, detail="Invalid path")
    
    target_pdf_dir = os.path.join(PDF_DIR, path)
    target_thumb_dir = os.path.join(THUMBNAIL_DIR, path)
    
    if not os.path.exists(target_pdf_dir):
        raise HTTPException(status_code=404, detail="Directory not found")
    
    if not os.path.isdir(target_pdf_dir):
        raise HTTPException(status_code=400, detail="Not a directory")

    items = os.listdir(target_pdf_dir)
    files = []
    directories = []

    for item in items:
        item_path = os.path.join(target_pdf_dir, item)
        if os.path.isdir(item_path):
            directories.append(item)
        elif item.lower().endswith('.pdf'):
            # Check for thumbnail
            thumb_name = os.path.splitext(item)[0] + ".jpg"
            thumb_path = os.path.join(target_thumb_dir, thumb_name)
            
            thumb_url = None
            if os.path.exists(thumb_path):
                # Construct URL
                # If path is empty, it's just /thumbnails/thumb_name
                # If path is subdir, it's /thumbnails/subdir/thumb_name
                rel_path = os.path.join(path, thumb_name).replace("\\", "/")
                thumb_url = f"/thumbnails/{rel_path}"
            else:
                # Trigger background generation
                background_tasks.add_task(generate_thumbnail_task, item_path, thumb_path)
            
            files.append({
                "name": item,
                "thumbnail": thumb_url
            })
            
    return {"files": files, "directories": directories, "current_path": path}

@app.get("/api/books/{path:path}/images")
def list_book_images(path: str):
    """
    Returns a list of image URLs for a given book (folder/zip name).
    path: relative path to the book folder in IMAGES_DIR (e.g. "subdir/bookname")
    """
    # Prevent directory traversal
    if ".." in path or path.startswith("/") or path.startswith("\\"):
         raise HTTPException(status_code=400, detail="Invalid path")
    
    target_dir = os.path.join(IMAGES_DIR, path)
    
    if not os.path.exists(target_dir):
        # It's possible the images haven't been extracted yet or don't exist.
        # For now, just return empty list or 404.
        # Let's return 404 to indicate "not found as image book".
        raise HTTPException(status_code=404, detail="Images not found")
    
    if not os.path.isdir(target_dir):
        raise HTTPException(status_code=400, detail="Not a directory")

    try:
        files = os.listdir(target_dir)
        # Filter for WebP (or other images) and sort
        images = [f for f in files if f.lower().endswith(('.webp', '.jpg', '.jpeg', '.png'))]
        
        # Sort naturally
        from natsort import natsorted
        images = natsorted(images)
        
        # Construct URLs
        image_urls = []
        for img in images:
            # URL encode path components if necessary?
            # FastAPI StaticFiles handles basic serving.
            # path is "subdir/bookname", img is "01.webp"
            # URL: /images/subdir/bookname/01.webp
            rel_path = os.path.join(path, img).replace("\\", "/")
            image_urls.append(f"/images/{rel_path}")
            
        return {"images": image_urls}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class DeletePagesRequest(BaseModel):
    page_indices: list[int]

@app.post("/api/pdfs/{filename}/delete_pages")
def delete_pages(filename: str, request: DeletePagesRequest, path: str = ""):
    # 1. Validate Path
    if ".." in path or path.startswith("/") or path.startswith("\\"):
         raise HTTPException(status_code=400, detail="Invalid path")
    
    target_pdf_dir = os.path.join(PDF_DIR, path)
    pdf_path = os.path.join(target_pdf_dir, filename)
    
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        # 2. Open PDF
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        # 3. Validate Indices
        indices = sorted(list(set(request.page_indices)), reverse=True) # Sort reverse to delete safely
        for idx in indices:
            if idx < 0 or idx >= total_pages:
                doc.close()
                raise HTTPException(status_code=400, detail=f"Invalid page index: {idx}")

        # 4. Delete Pages
        for idx in indices:
            doc.delete_page(idx)
        
        # 5. Save (Atomic-ish)
        # Save to temp file then rename
        temp_path = pdf_path + ".tmp"
        doc.save(temp_path)
        doc.close()
        
        # Replace original
        os.replace(temp_path, pdf_path)
        
        # 6. Regenerate Thumbnail if Page 0 was deleted
        # Or just always regenerate to be safe/simple? 
        # If page 0 was deleted, the new page 0 is different.
        # Let's regenerate if the file is not empty.
        
        doc_new = fitz.open(pdf_path)
        new_total = len(doc_new)
        
        if new_total > 0:
            # Thumbnail path
            thumb_name = os.path.splitext(filename)[0] + ".jpg"
            target_thumb_dir = os.path.join(THUMBNAIL_DIR, path)
            thumb_path = os.path.join(target_thumb_dir, thumb_name)
            
            # Generate new thumbnail
            page = doc_new.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
            pix.save(thumb_path)
            print(f"Regenerated thumbnail: {thumb_path}")
            
        doc_new.close()

        return {"message": "Pages deleted successfully", "total_pages": new_total}

    except Exception as e:
        if 'doc' in locals():
            doc.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"Hello": "World"}
