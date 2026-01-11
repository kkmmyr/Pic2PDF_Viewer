from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import os
import fitz
from services.pdf_generator import scan_and_generate
from config import *

router = APIRouter()

# Global state to track progress (retained here or moved to a shared state module?)
# For simplicity, keeping a simple simple in-memory state. 
# Shared state is tricky if routers are split.
# Let's simple keep it module level here, assuming only one worker process.
current_processing_item = None

class GenerateRequest(BaseModel):
    source_dir: str

@router.post("/generate")
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
        generated = scan_and_generate(request.source_dir, PDF_DIR, THUMBNAIL_DIR, IMAGES_DIR, COMPLETE_DIR, progress_callback)
        current_processing_item = None
        return {"message": "Generation complete", "files": generated}
    except Exception as e:
        current_processing_item = None
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
def get_status(source_dir: str):
    if not os.path.isdir(source_dir):
        return {"items": []}

    items_status = []
    
    for root, dirs, files in os.walk(source_dir):
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

class DeletePagesRequest(BaseModel):
    page_indices: list[int]

@router.post("/pdfs/{filename}/delete_pages")
def delete_pages(filename: str, request: DeletePagesRequest, path: str = "", source: str = "generated"):
    if ".." in path or path.startswith("/") or path.startswith("\\"):
         raise HTTPException(status_code=400, detail="Invalid path")
    
    if source == "kindle":
        base_pdf_dir = KINDLE_PDF_DIR
        base_thumb_dir = KINDLE_THUMBNAIL_DIR
    elif source == "novel":
        base_pdf_dir = KINDLE_NOVEL_PDF_DIR
        base_thumb_dir = KINDLE_NOVEL_THUMBNAIL_DIR
    else:
        base_pdf_dir = PDF_DIR
        base_thumb_dir = THUMBNAIL_DIR

    target_pdf_dir = os.path.join(base_pdf_dir, path)
    pdf_path = os.path.join(target_pdf_dir, filename)
    
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        indices = sorted(list(set(request.page_indices)), reverse=True)
        for idx in indices:
            if idx < 0 or idx >= total_pages:
                doc.close()
                raise HTTPException(status_code=400, detail=f"Invalid page index: {idx}")

        for idx in indices:
            doc.delete_page(idx)
        
        temp_path = pdf_path + ".tmp"
        doc.save(temp_path)
        doc.close()
        
        os.replace(temp_path, pdf_path)
        
        # Regenerate thumbnail if needed
        doc_new = fitz.open(pdf_path)
        new_total = len(doc_new)
        
        if new_total > 0:
            thumb_name = os.path.splitext(filename)[0] + ".jpg"
            target_thumb_dir = os.path.join(base_thumb_dir, path)
            thumb_path = os.path.join(target_thumb_dir, thumb_name)
            
            page = doc_new.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
            pix.save(thumb_path)
            print(f"Regenerated thumbnail: {thumb_path}")
            
        doc_new.close()

        return {"message": "Pages deleted successfully", "total_pages": new_total}

    except Exception as e:
        if 'doc' in locals() and doc:
            doc.close()
        raise HTTPException(status_code=500, detail=str(e))
