from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from services.ocr_service import ocr_service

router = APIRouter()

@router.post("/ocr/run")
def run_ocr(target_dir: Optional[str] = None):
    """
    Start the OCR batch process.
    target_dir is optional (if provided, passes --target-dir, otherwise runs default).
    """
    try:
        pid = ocr_service.start_ocr(target_dir)
        return {"status": "started", "pid": pid}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ocr/stop")
def stop_ocr():
    try:
        ocr_service.stop_ocr()
        return {"status": "stopped"}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class StatusResponse(BaseModel):
    status: str
    last_return_code: Optional[int]
    logs: List[str]

@router.get("/ocr/status", response_model=StatusResponse)
def get_ocr_status():
    return ocr_service.get_status()
