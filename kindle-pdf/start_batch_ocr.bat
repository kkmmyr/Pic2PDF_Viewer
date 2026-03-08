@echo off
REM Batch OCR processing with shared OCR venv
REM Add OCR module path
set PYTHONPATH=D:\61.tool\common\ocr;%PYTHONPATH%
D:\61.tool\common\ocr\venv\Scripts\python.exe "%~dp0batch_ocr.py" %*
