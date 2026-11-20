# 公開展示站部署（signaldesk.moreti.app）

公開站是 **PUBLIC_DEMO 唯讀沙盒**：資料為合成、投遞皆為本機模擬；非白名單的寫入（改品牌／專案／設定、建連結…）一律 403；白名單寫入每 IP 每 10 分鐘最多 60 次；資料庫每 6 小時自動重置。沒有任何金鑰，不呼叫付費服務。

## 目前的託管方式：Render 免費版（推薦）
- 以 repo 根目錄的 `render.yaml`（Blueprint）建立單一 Docker Web Service，方案 `free`。
- **閒置 15 分鐘會休眠，首次開啟可能要等約 1 分鐘**；重啟或休眠後 SQLite 會重置（公開站本來就定期重置，可接受）。
- 免費版每月 750 實例小時（整個帳號共用）；不要用定時 ping 強迫常駐（會耗盡時數，且平台不鼓勵）。要不休眠請改付費方案或 Fly.io。
- **API 與 worker 只能各一個實例**（worker 有 heartbeat 單例保護、SQLite 不適合多寫入）：不要水平擴展，`render.yaml` 已設 `numInstances: 1`。
- 容器入口 `deploy/entrypoint.sh` 讀平台提供的 `PORT`；健康檢查路徑 `/api/health`；以非 root 使用者執行。

### 首次部署
1. Render → New → Blueprint → 連接 GitHub repo → 確認方案為 Free → Deploy Blueprint。
2. 服務 Settings → Custom Domains 加入 `signaldesk.moreti.app`。
3. Cloudflare DNS：`signaldesk` 這筆 CNAME 指向 `signaldesk-lab.onrender.com`，**先設 DNS only（灰雲）**，待 Render 顯示已驗證與憑證已發放。

### 更新
改程式後同步到發佈資料夾並 push 到 `main`。`autoDeploy` 為關閉，需到 Render 服務頁按 **Manual Deploy**（或 Blueprint 的 Manual sync）。

### 驗證
```bash
curl https://signaldesk.moreti.app/api/health
curl -s -X POST -H 'Origin: https://signaldesk.moreti.app' -H 'Content-Type: application/json' -d '{"name":"x"}' https://signaldesk.moreti.app/api/brands   # 預期 403 public_demo_readonly
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Origin: https://signaldesk.moreti.app' 'https://signaldesk.moreti.app/api/projects/proj_toeic/run-now?sync=true'   # 預期 202
```
首頁頂端應出現「公開展示站」橫幅（由前端讀 `/api/settings` 的 `public_demo`）。

## 設定
`SIGNALDESK_PUBLIC_DEMO=1`、`SIGNALDESK_RESET_HOURS=6`、`SIGNALDESK_ORIGINS`、`SIGNALDESK_BASE_URL`、`TRACKING_ALLOWED_HOSTS`、`PORT`（見 `render.yaml`）。**不要在公開站設定 `ANTHROPIC_API_KEY`／`THREADS_ACCESS_TOKEN`。**

## 替代方案：自有 VPS（Caddy 自動 HTTPS）
`deploy/docker-compose.yml` + `deploy/Caddyfile`：DNS 設 A 記錄（先灰雲）、開放 80/443，`cd deploy && docker compose up -d --build`；更新用 `git pull && docker compose up -d --build`。此路徑**尚未在實際主機驗證**。Fly.io 也可直接使用同一個 Dockerfile（未實測）。

## 驗證狀態
- 本機 `docker build` 與以 `SIGNALDESK_PUBLIC_DEMO=1` 執行：health、唯讀 403、沙盒 202、非 root、無金鑰環境變數，已實測。
- Render 部署（onrender.com 與 signaldesk.moreti.app）：health、首頁 200、`public_demo:true`、403、202，已實測。
- 公開模式的限流與重置由 pytest 驗證（`test_public_demo_*`）；限流未在線上環境另行實測。
