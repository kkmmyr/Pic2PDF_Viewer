@echo off

REM Check if port 8766 is LISTENING
netstat -ano | findstr " :8766 " | findstr "LISTENING" > nul 2>&1

if %errorlevel% equ 0 (
    REM Backend is running -> kill uvicorn (start_server.bat loop will restart in same tab)
    echo Restarting Backend...
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr " :8766 " ^| findstr "LISTENING"') do (
        powershell -noprofile -command "$par=(gwmi Win32_Process -Filter 'ProcessId=%%p').ParentProcessId; Stop-Process -Id $par -Force -EA SilentlyContinue; Stop-Process -Id %%p -Force -EA SilentlyContinue"
    )
) else (
    REM Not running -> start Backend + Frontend
    wt new-tab --title "Backend" cmd /k "d:\61.tool\Pic2PDF_Viewer\backend\start_server.bat" ; new-tab --title "Frontend" cmd /k "cd /d D:\61.tool\Pic2PDF_Viewer\frontend && npm run dev"
)
