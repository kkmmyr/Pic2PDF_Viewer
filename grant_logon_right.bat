@echo off
setlocal

REM ======================================================================
REM Grant "Log on as a service" right (SeServiceLogonRight) to amashio.
REM Run as Administrator. Idempotent.
REM Needed when NSSM/services.msc fails to set service account credentials.
REM ======================================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Run this as Administrator.
    pause
    exit /b 1
)

powershell -noprofile -executionpolicy bypass -file "%~dp0grant_logon_right.ps1"
set RC=%errorlevel%

echo.
pause
exit /b %RC%
