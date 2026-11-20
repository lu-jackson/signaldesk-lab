# 真實使用模式：用獨立資料庫 data\real.db，啟動時不灌任何合成貼文，只放你自己匯入的內容。
# 用法（在專案根目錄）：
#   powershell -ExecutionPolicy Bypass -File scripts\real.ps1                 啟動（預設）
#   powershell -ExecutionPolicy Bypass -File scripts\real.ps1 upgrade         預覽品牌事實有哪些更新（不改品牌內容）
#   powershell -ExecutionPolicy Bypass -File scripts\real.ps1 upgrade-apply   確認升級品牌（新增版本，舊版保留）
# 只綁 127.0.0.1；不呼叫付費模型；投遞只寫本機模擬。要用 Live AI 請自己在 .env 設定金鑰（不要寫進程式或 git）。
param([ValidateSet("start", "upgrade", "upgrade-apply")][string]$Action = "start")

$root = Split-Path $PSScriptRoot -Parent
$env:SIGNALDESK_DB = Join-Path $root "data\real.db"
$env:SIGNALDESK_SYNTHETIC = "0"
New-Item -ItemType Directory -Force (Join-Path $root "data") | Out-Null

switch ($Action) {
    "start" {
        Write-Host "真實使用模式：資料庫 $env:SIGNALDESK_DB（不含合成資料）。開啟 http://127.0.0.1:8000 ，按 Ctrl+C 停止。"
        python "$PSScriptRoot\launcher.py" start
    }
    { $_ -in "upgrade", "upgrade-apply" } {
        $py = Join-Path $root "backend\.venv\Scripts\python.exe"
        if (-not (Test-Path $py)) { Write-Error "找不到 backend\.venv，請先執行：python scripts\launcher.py setup"; exit 1 }
        Push-Location (Join-Path $root "backend")
        try {
            if ($Action -eq "upgrade") { & $py -X utf8 -m app.seed --upgrade-brands }
            else { & $py -X utf8 -m app.seed --upgrade-brands --apply }
        } finally { Pop-Location }
    }
}
