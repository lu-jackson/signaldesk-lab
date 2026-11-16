# 安裝與啟動

> 實測範圍：**Windows 11 + Python 3.14.5 + Node 24.19.0**。macOS／Linux 的命令已撰寫（同一個 Python 啟動器），但**尚未實際執行過**。

## 需求
- Python **3.11+**（啟動器會檢查）。
- Node.js **20.19+ 或 22.12+**（Vite 8 的需求；啟動器會讀版本並提示）。
- 不需要 Docker、uv、pnpm、make。第一次安裝需要網路（pip / npm）；之後 Demo 運行完全不需要外部服務。

## 安裝（一次）

Windows（PowerShell）：
```bash
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```
macOS / Linux：
```bash
sh scripts/setup.sh
```
或任何平台：
```bash
python scripts/launcher.py setup
```
setup 會：建立 `backend/.venv`、用 `backend/requirements.lock.txt` 安裝鎖定版本、`npm ci`（用 `package-lock.json`）、`npm run build`、由 `.env.example` 建立 `.env`。

## 啟動
```bash
python scripts/launcher.py start
```
開啟 **http://127.0.0.1:8000**。這會：補齊 Demo 資料（不覆蓋你的修改）→ 啟動 API → 啟動**單一** worker（有 heartbeat 單例保護，重複啟動第二個 worker 會被拒絕）。只綁 127.0.0.1。

開發模式（前端熱更新，另開 http://127.0.0.1:5173，proxy 到 8000）：
```bash
python scripts/launcher.py dev
```
等價包裝：`scripts\dev.ps1 [start|dev]`、`sh scripts/dev.sh [start|dev]`。

## 停止與重啟
`Ctrl+C`（API 與 worker 一起關閉）。重啟只要再執行 `start`；資料在 `data/signaldesk.db`，不會遺失。工作中斷時 worker 的 lease 機制會處理（見 ARCHITECTURE）。

## Seed 與重設
```bash
python scripts/launcher.py seed              # 補缺的資料，不覆蓋
python scripts/launcher.py reset --confirm   # 清空 Demo DB 並重新 seed（破壞性；沒有 --confirm 只會警告）
```
seed 用固定 random seed：同一天結果一致；隔天只會把貼文時間平移，所以「最近七天」不會變空。

## 測試
```bash
python scripts/launcher.py test   # 後端 pytest + 前端 typecheck/build
python scripts/launcher.py e2e    # Playwright（需先 build 前端；使用本機 Edge/Chrome，沒有就用 Playwright 的 chromium）
```
若要用 Playwright 內建 chromium：`backend/.venv/Scripts/python -m playwright install chromium`（約 150 MB，非必需）。

## 環境變數（`.env`，皆為選填）
| 變數 | 用途 |
|---|---|
| `SIGNALDESK_DB` | DB 路徑（預設 `data/signaldesk.db`） |
| `SIGNALDESK_PORT` | 啟動器的 API port（預設 8000） |
| `SIGNALDESK_BASE_URL` | 短連結顯示用 base URL |
| `SIGNALDESK_ORIGINS` | 額外允許的寫入 Origin |
| `TRACKING_ALLOWED_HOSTS` | 追蹤連結可指向的主機（預設 127.0.0.1,localhost） |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Live AI；**兩個都有**才會使用，且要在 UI「設定」切 AI_PROVIDER。會產生費用 |
| `THREADS_ACCESS_TOKEN` | Threads 唯讀搜尋；未實測 |

三個模式開關互相獨立：`SOCIAL_SOURCE`（demo｜threads_readonly）、`AI_PROVIDER`（demo｜anthropic）存在 DB、由 UI 切換；`DELIVERY_MODE` 固定為 simulation，沒有任何可開啟真實發送的選項。

## 常見問題
- 首頁空白：先 `npm run build`（FastAPI 只供應 `frontend/dist`）；或用 `dev` 模式。
- Run Now 一直 queued：worker 沒在跑（儀表板會提示）。用 `start`，或另開終端機 `cd backend && .venv\Scripts\python -m app.worker`。
- 「已有 worker 在執行」：單例保護，另一個 worker 還活著（15 秒內有 heartbeat）。
- 版本錯誤：`python scripts/launcher.py check` 會說明缺什麼。
