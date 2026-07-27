@echo off
setlocal enabledelayedexpansion

REM ======================================================================
REM Pic2PDF Viewer - Windows Service installer (via NSSM)
REM Run this as Administrator (Right-click -> Run as administrator).
REM Idempotent: safe to re-run; existing service will be replaced.
REM ======================================================================

REM --- Admin check ----------------------------------------------------
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] This script must be run as Administrator.
    echo Right-click the file and choose "Run as administrator".
    pause
    exit /b 1
)

REM --- Paths ----------------------------------------------------------
set "NSSM=C:\Users\amashio\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
set "SVC=Pic2PDFViewer"
set "ROOT=D:\61.tool\Pic2PDF_Viewer"
set "BACKEND=%ROOT%\backend"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "LOGDIR=%BACKEND%\data\logs"

REM --- Sanity checks --------------------------------------------------
if not exist "%NSSM%" (
    echo [ERROR] nssm.exe not found at:
    echo   %NSSM%
    echo Try: winget install NSSM.NSSM
    pause
    exit /b 1
)
if not exist "%PY%" (
    echo [ERROR] python.exe not found at:
    echo   %PY%
    echo Make sure the backend venv exists ^(cd backend ^&^& uv sync^).
    pause
    exit /b 1
)
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo === Pic2PDF Viewer Service Setup ===
echo NSSM    : %NSSM%
echo Service : %SVC%
echo Python  : %PY%
echo WorkDir : %BACKEND%
echo LogDir  : %LOGDIR%
echo.

REM --- Remove existing service if present -----------------------------
"%NSSM%" status "%SVC%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Existing service detected. Stopping and removing first...
    "%NSSM%" stop "%SVC%" >nul 2>&1
    timeout /t 2 /nobreak >nul
    "%NSSM%" remove "%SVC%" confirm >nul 2>&1
    timeout /t 1 /nobreak >nul
)

REM --- Install --------------------------------------------------------
echo [STEP] Installing service...
"%NSSM%" install "%SVC%" "%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8090
if %errorlevel% neq 0 (
    echo [ERROR] nssm install failed.
    pause
    exit /b 1
)

REM --- App settings ---------------------------------------------------
"%NSSM%" set "%SVC%" AppDirectory "%BACKEND%"
"%NSSM%" set "%SVC%" DisplayName "Pic2PDF Viewer"
"%NSSM%" set "%SVC%" Description "Pic2PDF Viewer release server (FastAPI/uvicorn on :8090). Auto-restart on crash."

REM Delayed auto-start: give OneDrive/network a moment after boot
"%NSSM%" set "%SVC%" Start SERVICE_DELAYED_AUTO_START

REM Crash recovery: restart with 5s delay, but throttle if it dies within 10s
"%NSSM%" set "%SVC%" AppThrottle 10000
"%NSSM%" set "%SVC%" AppExit Default Restart
"%NSSM%" set "%SVC%" AppRestartDelay 5000

REM On stop: kill the whole process tree (OCR/yomitoku subprocesses etc.)
"%NSSM%" set "%SVC%" AppKillProcessTree 1
"%NSSM%" set "%SVC%" AppStopMethodSkip 0
"%NSSM%" set "%SVC%" AppStopMethodConsole 15000

REM Log redirection with rotation (10MB / 24h)
"%NSSM%" set "%SVC%" AppStdout "%LOGDIR%\service-stdout.log"
"%NSSM%" set "%SVC%" AppStderr "%LOGDIR%\service-stderr.log"
"%NSSM%" set "%SVC%" AppRotateFiles 1
"%NSSM%" set "%SVC%" AppRotateOnline 1
"%NSSM%" set "%SVC%" AppRotateBytes 10485760
"%NSSM%" set "%SVC%" AppRotateSeconds 86400

REM Env: keep prior fix (UTF-8 to avoid CP932 surprises with subprocess pipes)
"%NSSM%" set "%SVC%" AppEnvironmentExtra PYTHONIOENCODING=utf-8

echo.
echo [OK] Service installed and configured.
echo.
echo ============================================================
echo NEXT STEP - Log on account configuration ^(REQUIRED^)
echo ============================================================
echo.
echo  The service is currently set to run as LocalSystem.
echo  It MUST run as your user account so it can access OneDrive
echo  and your data files.
echo.
echo  Pressing any key will open the NSSM service editor:
echo    1. Click the "Log on" tab
echo    2. Select "This account"
echo    3. Username : .\amashio
echo    4. Password : ^(your Windows login password, twice^)
echo    5. Click OK
echo.
pause

"%NSSM%" edit "%SVC%"

echo.
echo ============================================================
echo Setup complete.
echo ============================================================
echo.
echo  Start the service now :  nssm start %SVC%
echo  Check status          :  Get-Service %SVC%
echo  Tail logs             :  Get-Content "%LOGDIR%\service-stdout.log" -Tail 50 -Wait
echo  Restart ^(after build^) :  restart_service.bat
echo  Remove                :  nssm stop %SVC% ^&^& nssm remove %SVC% confirm
echo.
pause
endlocal
