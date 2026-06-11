@echo off
chcp 65001 > nul
cd /d %~dp0\..\frontend

echo === Pic2PDF_Viewer release build ===
echo.

call npm run build
if errorlevel 1 (
    echo.
    echo [NG] build failed.
    pause
    exit /b 1
)

echo.
echo [OK] dist/ updated.
echo.
echo Next step: run restart_service.bat (as Administrator) to reload code.
echo.
pause
