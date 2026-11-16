# 在本機以「公開展示模式」啟動（給 Cloudflare Tunnel 轉發用）。只綁 127.0.0.1:8090。
# 用法：powershell -ExecutionPolicy Bypass -File scripts\public_demo.ps1
$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
$env:SIGNALDESK_PUBLIC_DEMO = "1"
$env:SIGNALDESK_RESET_HOURS = "6"
$env:SIGNALDESK_DB = Join-Path $root "data\public_demo.db"
$env:SIGNALDESK_ORIGINS = "https://signaldesk.moreti.app"
$env:SIGNALDESK_BASE_URL = "https://signaldesk.moreti.app"
$env:TRACKING_ALLOWED_HOSTS = "signaldesk.moreti.app,127.0.0.1,localhost"
$env:PYTHONUTF8 = "1"
Set-Location (Join-Path $root "backend")
& $py -m app.seed
$worker = Start-Process $py -ArgumentList "-m","app.worker" -PassThru -NoNewWindow
try { & $py -m uvicorn app.main:app_factory --factory --host 127.0.0.1 --port 8090 --proxy-headers --forwarded-allow-ips="127.0.0.1" }
finally { Stop-Process -Id $worker.Id -Force -ErrorAction SilentlyContinue }
