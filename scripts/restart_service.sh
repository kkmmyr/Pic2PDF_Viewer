#!/bin/bash
# Linux 版サービス再起動スクリプト（restart_service.bat の代替）
sudo systemctl restart pic2pdf-viewer
sudo systemctl status pic2pdf-viewer --no-pager
echo ""
echo "Tail logs:"
echo "  journalctl -u pic2pdf-viewer -f"
echo "  tail -f /opt/pic2pdf-viewer/logs/service-stdout.log"
