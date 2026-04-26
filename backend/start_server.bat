@echo off
cd /d %~dp0

echo Syncing dependencies with uv...
uv sync

echo Starting Backend Server...
uv run uvicorn main:app --reload --port 8000
