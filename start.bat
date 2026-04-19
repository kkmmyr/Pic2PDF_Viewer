@echo off
chcp 65001 > nul

wt new-tab --title "Backend" cmd /k "d:\61.tool\Pic2PDF_Viewer\backend\start_server.bat" ; new-tab --title "Frontend" cmd /k "cd /d D:\61.tool\Pic2PDF_Viewer\frontend && npm run dev"
