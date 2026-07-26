@echo off
setlocal
cd /d "%~dp0..\backend"
uv run python ocr_agent.py
endlocal
