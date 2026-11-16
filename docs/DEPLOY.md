# 公開展示站部署（signaldesk.moreti.app）

公開站是 **PUBLIC_DEMO 唯讀沙盒**：資料為合成、投遞皆為本機模擬；非白名單的寫入（改品牌／專案／設定、建連結…）一律 403；白名單寫入每 IP 每 10 分鐘最多 60 次；資料庫每 6 小時自動重置。沒有任何金鑰，不呼叫付費服務。

## 步驟
1. **DNS**（Cloudflare）：新增 `A` 記錄 `signaldesk` → VPS 公網 IP，**先設為 DNS only（灰雲）**，讓 Caddy 能自動取得憑證。
2. **VPS**：安裝 Docker 與 compose plugin，開放 80/443。
3. 取得程式碼並啟動：
```bash
git clone <this repo> signaldesk-lab && cd signaldesk-lab/deploy
docker compose up -d --build
```
4. 驗證：`curl https://signaldesk.moreti.app/api/health`，並確認首頁頂端出現「公開展示站」橫幅。
5. 更新：`git pull && docker compose up -d --build`。停止：`docker compose down`（資料在 volume `appdata`）。

## 設定（見 `deploy/docker-compose.yml`）
`SIGNALDESK_PUBLIC_DEMO=1`、`SIGNALDESK_RESET_HOURS=6`、`SIGNALDESK_ORIGINS`、`TRACKING_ALLOWED_HOSTS`。不要在公開站設定 `ANTHROPIC_API_KEY`／`THREADS_ACCESS_TOKEN`。

## 狀態
`deploy/` 的映像與 compose 檔依本機測試過的程式撰寫；公開模式的限制已由 pytest 驗證（`test_public_demo_*`），但**容器映像是否能在目標主機成功建置，以實際部署結果為準**。
