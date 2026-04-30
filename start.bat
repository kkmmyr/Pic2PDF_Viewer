@echo off
chcp 65001 > nul

REM ポート 8766 が LISTENING 状態か確認
netstat -ano | findstr " :8766 " | findstr "LISTENING" > nul 2>&1

if %errorlevel% equ 0 (
    REM --- 起動中 → uvicorn を終了（start_server.bat のループが同タブで再起動する）
    echo Backend を再起動します...
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr " :8766 " ^| findstr "LISTENING"') do (
        powershell -noprofile -command "$par=(gwmi Win32_Process -Filter 'ProcessId=%%p').ParentProcessId; Stop-Process -Id $par -Force -EA SilentlyContinue; Stop-Process -Id %%p -Force -EA SilentlyContinue"
    )
) else (
    REM --- 未起動 → Backend + Frontend 両方起動 ---
    wt new-tab --title "Backend" cmd /k "d:\61.tool\Pic2PDF_Viewer\backend\start_server.bat" ; new-tab --title "Frontend" cmd /k "cd /d D:\61.tool\Pic2PDF_Viewer\frontend && npm run dev"
)
