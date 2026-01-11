from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import os
import shutil
import fitz
from typing import Optional, List
from config import *

router = APIRouter()

def generate_thumbnail_task(pdf_path: str, thumbnail_path: str):
    try:
        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
        doc = fitz.open(pdf_path)
        if len(doc) > 0:
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
            pix.save(thumbnail_path)
            print(f"Generated thumbnail: {thumbnail_path}")
        doc.close()
    except Exception as e:
        print(f"Failed to generate thumbnail for {pdf_path}: {e}")

@router.get("/pdfs")
def list_pdfs(background_tasks: BackgroundTasks, path: str = "", source: str = "generated"):
    if ".." in path or path.startswith("/") or path.startswith("\\"):
         raise HTTPException(status_code=400, detail="Invalid path")
    
    if source == "kindle":
        base_pdf_dir = KINDLE_PDF_DIR
        base_thumb_dir = KINDLE_THUMBNAIL_DIR
        url_prefix_thumb = "/kindle/thumbnails"
    elif source == "novel":
        base_pdf_dir = KINDLE_NOVEL_PDF_DIR
        base_thumb_dir = KINDLE_NOVEL_THUMBNAIL_DIR
        url_prefix_thumb = "/kindle_novel/thumbnails"
    else:
        base_pdf_dir = PDF_DIR
        base_thumb_dir = THUMBNAIL_DIR
        url_prefix_thumb = "/thumbnails"

    target_pdf_dir = os.path.join(base_pdf_dir, path)
    target_thumb_dir = os.path.join(base_thumb_dir, path)
    
    if not os.path.exists(target_pdf_dir):
        return {"files": [], "directories": [], "current_path": path}
    
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
            thumb_name = os.path.splitext(item)[0] + ".jpg"
            thumb_path = os.path.join(target_thumb_dir, thumb_name)
            
            thumb_url = None
            if os.path.exists(thumb_path):
                rel_path = os.path.join(path, thumb_name).replace("\\", "/")
                thumb_url = f"{url_prefix_thumb}/{rel_path}"
            else:
                background_tasks.add_task(generate_thumbnail_task, item_path, thumb_path)
            
            files.append({
                "name": item,
                "thumbnail": thumb_url
            })
            
    return {"files": files, "directories": directories, "current_path": path}

@router.get("/books/{path:path}/images")
def list_book_images(path: str, source: str = "generated"):
    if ".." in path or path.startswith("/") or path.startswith("\\"):
         raise HTTPException(status_code=400, detail="Invalid path")
    
    if source == "kindle":
        base_images_dir = KINDLE_IMAGES_DIR
        url_prefix = "/kindle/images"
    elif source == "novel":
        base_images_dir = KINDLE_NOVEL_IMAGES_DIR
        url_prefix = "/kindle_novel/images"
    else:
        base_images_dir = IMAGES_DIR
        url_prefix = "/images"

    target_dir = os.path.join(base_images_dir, path)
    
    if not os.path.exists(target_dir):
        raise HTTPException(status_code=404, detail="Images not found")
    
    if not os.path.isdir(target_dir):
        raise HTTPException(status_code=400, detail="Not a directory")

    try:
        files = os.listdir(target_dir)
        images = [f for f in files if f.lower().endswith(('.webp', '.jpg', '.jpeg', '.png'))]
        
        from natsort import natsorted
        images = natsorted(images)
        
        image_urls = []
        for img in images:
            rel_path = os.path.join(path, img).replace("\\", "/")
            image_urls.append(f"{url_prefix}/{rel_path}")
            
        return {"images": image_urls}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CreateDirectoryRequest(BaseModel):
    path: str
    name: str
    source: str = "generated"

@router.post("/directories")
def create_directory(request: CreateDirectoryRequest):
    if request.source == "kindle":
        base_pdf_dir = KINDLE_PDF_DIR
    elif request.source == "novel":
        base_pdf_dir = KINDLE_NOVEL_PDF_DIR
    else:
        base_pdf_dir = PDF_DIR

    target_dir = os.path.join(base_pdf_dir, request.path, request.name)
    
    if ".." in request.path or ".." in request.name:
        raise HTTPException(status_code=400, detail="Invalid path")

    if os.path.exists(target_dir):
        raise HTTPException(status_code=400, detail="Directory already exists")

    try:
        os.makedirs(target_dir)
        return {"message": "Directory created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MoveItemsRequest(BaseModel):
    items: list[str]
    source_path: str
    destination_path: str
    source: str = "generated"

@router.post("/move")
def move_items(request: MoveItemsRequest):
    if ".." in request.source_path or ".." in request.destination_path:
        raise HTTPException(status_code=400, detail="Invalid path")
        
    for item in request.items:
        if ".." in item:
            raise HTTPException(status_code=400, detail="Invalid item name")

    if request.source == "kindle":
        dirs = {
            "pdf": KINDLE_PDF_DIR,
            "thumb": KINDLE_THUMBNAIL_DIR,
            "img": KINDLE_IMAGES_DIR
        }
    elif request.source == "novel":
        dirs = {
            "pdf": KINDLE_NOVEL_PDF_DIR,
            "thumb": KINDLE_NOVEL_THUMBNAIL_DIR,
            "img": KINDLE_NOVEL_IMAGES_DIR
        }
    else:
        dirs = {
            "pdf": PDF_DIR,
            "thumb": THUMBNAIL_DIR,
            "img": IMAGES_DIR
        }

    moved_count = 0
    errors = []

    for item in request.items:
        try:
            src_pdf = os.path.join(dirs["pdf"], request.source_path, item)
            dst_pdf = os.path.join(dirs["pdf"], request.destination_path, item)
            
            if not os.path.exists(src_pdf):
                errors.append(f"Item not found: {item}")
                continue
                
            if os.path.exists(dst_pdf):
                errors.append(f"Destination exists: {item}")
                continue
            
            os.makedirs(os.path.dirname(dst_pdf), exist_ok=True)
            shutil.move(src_pdf, dst_pdf)
            
            if os.path.isdir(dst_pdf):
                src_thumb = os.path.join(dirs["thumb"], request.source_path, item)
                dst_thumb = os.path.join(dirs["thumb"], request.destination_path, item)
                if os.path.exists(src_thumb):
                    os.makedirs(os.path.dirname(dst_thumb), exist_ok=True)
                    shutil.move(src_thumb, dst_thumb)
            else:
                thumb_name = os.path.splitext(item)[0] + ".jpg"
                src_thumb = os.path.join(dirs["thumb"], request.source_path, thumb_name)
                dst_thumb = os.path.join(dirs["thumb"], request.destination_path, thumb_name)
                if os.path.exists(src_thumb):
                    os.makedirs(os.path.dirname(dst_thumb), exist_ok=True)
                    shutil.move(src_thumb, dst_thumb)

            book_name = item
            if item.lower().endswith('.pdf'):
                book_name = os.path.splitext(item)[0]
                
            src_img = os.path.join(dirs["img"], request.source_path, book_name)
            dst_img = os.path.join(dirs["img"], request.destination_path, book_name)
            
            if os.path.exists(src_img):
                 os.makedirs(os.path.dirname(dst_img), exist_ok=True)
                 shutil.move(src_img, dst_img)

            moved_count += 1

        except Exception as e:
            errors.append(f"Error moving {item}: {str(e)}")

    if moved_count == 0 and errors:
        raise HTTPException(status_code=500, detail="Failed to move items: " + "; ".join(errors))

    return {"message": "Items moved", "moved_count": moved_count, "errors": errors}
