@echo off
chcp 65001 > nul
echo ========================================
echo Pic2PDF Viewer 起動スクリプト
echo ========================================
echo.

echo [1/2] Starting Backend Server... (Port 8000)
start "Backend - Pic2PDF Viewer" cmd /k "d:\61.tool\Pic2PDF_Viewer\backend\start_server.bat"

echo [2/2] Starting Frontend Server... (Port 5173)
timeout /t 3 /nobreak > nul
start "Frontend - Pic2PDF Viewer" cmd /k "cd /d D:\61.tool\Pic2PDF_Viewer\frontend && npm run dev"

echo.
echo ========================================
echo Servers are up and running!
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo ========================================
echo.
echo You can create this window now.
pause