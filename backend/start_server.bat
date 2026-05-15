@echo off
cd /d %~dp0

:restart
echo ----------------------------------------
echo Syncing dependencies with uv...
uv sync

echo Starting Backend Server...
uv run uvicorn main:app --reload --reload-dir . --reload-exclude "tests" --reload-exclude "scripts" --port 8766

echo.
echo Backend stopped. Restarting in 3s... (Ctrl+C + Y to stop)
timeout /t 3 /nobreak > nul
goto :restart
