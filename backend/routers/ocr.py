from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import subprocess
import os
import sys
import threading
import queue
import time
from collections import deque
from typing import List, Optional
from config import OCR_PYTHON_PATH, BATCH_OCR_SCRIPT

router = APIRouter()

# Global state
class OCRState:
    process: Optional[subprocess.Popen] = None
    status: str = "idle" # idle, running, error
    logs: deque = deque(maxlen=2000) # Keep last 2000 lines
    last_return_code: Optional[int] = None

state = OCRState()

def log_reader(proc: subprocess.Popen, log_queue: deque):
    """Reads stdout lines from process and appends to log queue."""
    # Read output line by line
    # We merge stdout and stderr
    for line in iter(proc.stdout.readline, b''):
        decoded = line.decode('utf-8', errors='replace').rstrip()
        log_queue.append(decoded)
    proc.stdout.close()

@router.post("/ocr/run")
def run_ocr(target_dir: Optional[str] = None):
    """
    Start the OCR batch process.
    target_dir is optional (if provided, passes --target-dir, otherwise runs default).
    """
    if state.status == "running":
        if state.process and state.process.poll() is None:
            raise HTTPException(status_code=400, detail="OCR process is already running")
        else:
            # Cleanup zombie state check
            state.status = "idle"

    try:
        # Prepare command
        cmd = [OCR_PYTHON_PATH, BATCH_OCR_SCRIPT]
        
        # Note: BATCH_OCR_SCRIPT currently defaults to processing all.
        # If we want to support arguments later, we can add them to cmd.
        
        # Start Process
        # Use unbuffered output (-u) for python or force flush
        # But we're launching a script.
        # Adding -u to python executable args might help if python
        cmd.insert(1, "-u") 

        # Force UTF-8 output
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        state.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr to stdout
            bufsize=1, # Line buffered
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            env=env
        )
        state.status = "running"
        state.last_return_code = None
        state.logs.clear()
        state.logs.append(f"Starting OCR process: {' '.join(cmd)}")

        # Start Log Reader Thread
        t = threading.Thread(target=log_reader, args=(state.process, state.logs), daemon=True)
        t.start()
        
        # Start Monitor Thread to update status when done
        t_monitor = threading.Thread(target=process_monitor, args=(state.process,), daemon=True)
        t_monitor.start()

        return {"status": "started", "pid": state.process.pid}

    except Exception as e:
        state.status = "error"
        state.logs.append(f"Failed to start process: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def process_monitor(proc):
    proc.wait()
    state.last_return_code = proc.returncode
    state.status = "idle"
    if proc.returncode == 0:
        state.logs.append("Process finished successfully.")
    else:
        state.logs.append(f"Process finished with error code: {proc.returncode}")

@router.post("/ocr/stop")
def stop_ocr():
    if state.status != "running" or not state.process:
        raise HTTPException(status_code=400, detail="No running process to stop")
    
    try:
        state.process.terminate()
        state.logs.append("Sent TERMINATE signal...")
        try:
            state.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            state.process.kill()
            state.logs.append("Sent KILL signal...")
        
        state.status = "idle"
        return {"status": "stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class StatusResponse(BaseModel):
    status: str
    last_return_code: Optional[int]
    logs: List[str]

@router.get("/ocr/status", response_model=StatusResponse)
def get_ocr_status():
    # Only return logs if requested? Or return last N lines?
    # For simplicity, return all logs in buffer (max 2000 lines is handled by deque)
    return {
        "status": state.status,
        "last_return_code": state.last_return_code,
        "logs": list(state.logs)
    }
