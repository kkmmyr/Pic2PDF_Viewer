@echo off
chcp 65001 > nul
cd /d %~dp0\backend

if not exist "..\frontend\dist\index.html" (
    echo [NG] frontend\dist\index.html not found.
    echo Please run build_release.bat first.
    pause
    exit /b 1
)

echo === Pic2PDF_Viewer release server ===
echo URL: http://localhost:8090
echo.

REM Skip browser auto-launch when called with --no-browser
if not "%1"=="--no-browser" start "" "http://localhost:8090"

:loop
uv run uvicorn main:app --host 127.0.0.1 --port 8090
if %errorlevel% equ 0 goto :end
echo.
echo [WARN] Server exited with code %errorlevel%. Restarting in 5 seconds...
timeout /t 5 /nobreak > nul
goto :loop
:end
