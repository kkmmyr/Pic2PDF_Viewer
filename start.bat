@echo off
chcp 65001 > nul
echo ========================================
echo Pic2PDF Viewer 起動スクリプト
echo ========================================
echo.

echo [1/2] バックエンドサーバーを起動中... (Port 8000)
start "Backend - Pic2PDF Viewer" cmd /k "cd /d F:\61.tool\Pic2PDF_Viewer\backend && python -m uvicorn main:app --reload --port 8000"

echo [2/2] フロントエンドサーバーを起動中... (Port 5173)
timeout /t 3 /nobreak > nul
start "Frontend - Pic2PDF Viewer" cmd /k "cd /d F:\61.tool\Pic2PDF_Viewer\frontend && npm run dev"

echo.
echo ========================================
echo 両サーバーが起動しました！
echo バックエンド: http://localhost:8000
echo フロントエンド: http://localhost:5173
echo ========================================
echo.
echo このウィンドウは閉じても大丈夫です。
pause
