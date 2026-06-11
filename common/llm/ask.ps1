# ask.ps1 - ask.py の PowerShell ラッパー
# 使い方: .\ask.ps1 "質問"
#         .\ask.ps1 -f code.py "レビューして"
#         .\ask.ps1 --think "難しい論理パズル"
#         .\ask.ps1 --session
#         cat file.txt | .\ask.ps1 "論点を整理して"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$scriptDir\ask.py" @args
