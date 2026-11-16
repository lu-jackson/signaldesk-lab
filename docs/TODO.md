# 待辦事項

## 常駐託管公開展示站（目前跑在開發者自己的電腦，關機就下線）
- [ ] 選一個常駐主機：託管平台（Fly.io／Render／Railway，建議）或小型 VPS。
- [ ] 用 `deploy/Dockerfile` 實際建置映像並驗證（本機 Docker 尚未驗證過）。
- [ ] SQLite 需要持久磁碟或接受每次重啟重置（公開站本來就每 6 小時重置）。
- [ ] Cloudflare：把 `signaldesk` 改指向新主機（CNAME 或 A），並停用本機 tunnel。
- [ ] 驗證 `/api/health`、首頁公開站橫幅、寫入 403 與限流。

## 內容維護
- [ ] 官網價格或方案變動時，更新 `backend/app/seed.py` 的品牌事實。
