<#
.SYNOPSIS
    backend/data を OneDrive へ差分バックアップする。

.DESCRIPTION
    robocopy で D:\61.tool\Pic2PDF_Viewer\backend\data を
    C:\Users\<user>\OneDrive\61.tool\Pic2PDF_Viewer_backup へミラーリングする。
    タスクスケジューラから週次実行することを想定。
    ログは %TEMP%\pic2pdf_backup.log に追記する。

.EXAMPLE
    & "D:\61.tool\Pic2PDF_Viewer\tools\backup_data.ps1"
    & "D:\61.tool\Pic2PDF_Viewer\tools\backup_data.ps1" -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$SourceDir = "D:\61.tool\Pic2PDF_Viewer\backend\data",
    [string]$BackupDir = "C:\Users\$env:USERNAME\OneDrive\61.tool\Pic2PDF_Viewer_backup",
    [string]$LogFile   = "$env:TEMP\pic2pdf_backup.log"
)

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

if (-not (Test-Path $SourceDir)) {
    $msg = "[$timestamp] ERROR: Source not found: $SourceDir"
    Write-Error $msg
    Add-Content -Path $LogFile -Value $msg -Encoding UTF8
    exit 1
}

Write-Host "[$timestamp] Backup start" -ForegroundColor Cyan
Write-Host "  Source : $SourceDir"
Write-Host "  Dest   : $BackupDir"
Write-Host "  Log    : $LogFile"

Add-Content -Path $LogFile -Value "" -Encoding UTF8
Add-Content -Path $LogFile -Value "=== $timestamp Backup start ===" -Encoding UTF8
Add-Content -Path $LogFile -Value "  Source: $SourceDir" -Encoding UTF8
Add-Content -Path $LogFile -Value "  Dest  : $BackupDir" -Encoding UTF8

if ($WhatIfPreference) {
    Write-Host "[WhatIf] Dry run only." -ForegroundColor Yellow
    & robocopy $SourceDir $BackupDir /MIR /FFT /Z /NP /L
} else {
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    }
    # /MIR: mirror  /FFT: FAT timestamp tolerance  /Z: restartable
    # /NP: no progress  /R:3 /W:5: retry  /LOG+: append log
    & robocopy $SourceDir $BackupDir /MIR /FFT /Z /NP /R:3 /W:5 /LOG+:$LogFile
}

$exitCode = $LASTEXITCODE
$endTime  = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# robocopy exit code: 0-7 = success, 8+ = error
if ($exitCode -le 7) {
    $msg = "[$endTime] Done (exitCode=$exitCode)"
    Write-Host $msg -ForegroundColor Green
    Add-Content -Path $LogFile -Value $msg -Encoding UTF8
    exit 0
} else {
    $msg = "[$endTime] ERROR (exitCode=$exitCode)"
    Write-Error $msg
    Add-Content -Path $LogFile -Value $msg -Encoding UTF8
    exit 1
}
