@echo off
setlocal
cd /d "%~dp0\.."
uv run --project kindle-pdf python kindle-pdf\capture_agent.py
endlocal
