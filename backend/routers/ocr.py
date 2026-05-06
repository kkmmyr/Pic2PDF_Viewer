
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from routers._deps import log_and_raise_500
from services.ocr_service import ocr_service

router = APIRouter()

@router.post("/ocr/run")
@log_and_raise_500("ocr/run")
def run_ocr(target_dir: str | None = None):
    try:
        pid = ocr_service.start_ocr(target_dir)
        return {"status": "started", "pid": pid}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

@router.post("/ocr/stop")
@log_and_raise_500("ocr/stop")
def stop_ocr():
    try:
        ocr_service.stop_ocr()
        return {"status": "stopped"}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

class StatusResponse(BaseModel):
    status: str
    last_return_code: int | None
    logs: list[str]

@router.get("/ocr/status", response_model=StatusResponse)
def get_ocr_status():
    return ocr_service.get_status()
