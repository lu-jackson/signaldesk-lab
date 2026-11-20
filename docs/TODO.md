# 待辦事項

## 已完成：常駐託管公開展示站
- [x] 託管於 Render 免費版（`render.yaml`），網址 https://signaldesk.moreti.app（見 docs/DEPLOY.md）。
- [x] 本機 Docker 建置與驗證；線上 health／403／202 驗證。
- [x] Cloudflare `signaldesk` CNAME 已指向 Render。
- [ ] 使用者端：停止本機 Cloudflare tunnel 與 `scripts/public_demo.ps1`（不再需要）。

## 可選改進
- [ ] 免費版會休眠；若要不休眠可改 Fly.io（約 US$2–4/月）或 Render Starter（US$7/月）。
- [ ] 在 Render 或 Cloudflare 設定 Cloudflare 橘雲（Proxied）前，先確認憑證續期不受影響。

## 內容維護
- [ ] 官網價格或方案變動時，更新 `backend/app/seed.py` 的品牌事實。
