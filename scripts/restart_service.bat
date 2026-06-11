@echo off
REM Restart the Pic2PDF Viewer service. Use this after build_release.bat
REM to reload new code into the running server.
REM Requires Administrator privileges (auto-elevates via PowerShell UAC prompt).

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -noprofile -command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo === Pic2PDF Viewer service restart ===
powershell -noprofile -command "try { Restart-Service Pic2PDFViewer -ErrorAction Stop; Start-Sleep -Seconds 2; Get-Service Pic2PDFViewer | Format-Table Name, Status, StartType -AutoSize } catch { Write-Host '[ERROR] Restart failed:' $_.Exception.Message -ForegroundColor Red; exit 1 }"
if %errorlevel% neq 0 (
    pause
    exit /b 1
)
echo Tail logs with:
echo   Get-Content "D:\61.tool\Pic2PDF_Viewer\backend\data\logs\service-stdout.log" -Tail 30 -Wait
pause
