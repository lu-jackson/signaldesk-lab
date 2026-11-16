# Windows：啟動 API + worker + 前端。用法：powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 [start|dev]
param([string]$Mode = "start")
python "$PSScriptRoot\launcher.py" $Mode
