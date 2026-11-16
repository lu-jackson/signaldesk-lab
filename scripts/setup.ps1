# Windows：一次安裝。用法：powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { Write-Error "找不到 python（需要 3.11+）。請先安裝。"; exit 1 }
python "$PSScriptRoot\launcher.py" setup
