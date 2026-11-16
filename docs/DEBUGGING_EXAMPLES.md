# 三個可安全重現的錯誤

三個都只動本機 Demo 資料，不會送出任何東西。做完後用 `python scripts/launcher.py reset --confirm` 可回到乾淨狀態（會清掉你自己的修改）。

---

## 1. 「模擬送出」按不了／回 409

**症狀**：草稿頁「模擬送出」是灰的；用 API 直接送會得到 `409 {"error":{"code":"approval_required",...}}`。

**重現**
1. 草稿頁核准一份草稿，確認「核准有效」。
2. 把內文改一個字，按「儲存修改」。
3. 嘗試送出：
```bash
curl -X POST http://127.0.0.1:8000/api/drafts/<draft_id>/simulate-send
```

**怎麼看 trace**
```bash
curl http://127.0.0.1:8000/api/drafts/<draft_id>
```
看 `status`（回到 `draft`）、`revision`（+1）、`approval_valid`（`false`）。再看資料庫 `approvals` 表該草稿的列：`revoked_at` 有值。

**原因與修復**：修改內容 → `drafts.edit_draft` 撤銷核准並重算 `content_hash`；`simulate_send` 要求「狀態 approved 且核准 hash＝目前 hash」。修復就是**重新核准**（`POST /api/drafts/<id>/approve`）。這不是 bug，是設計（單元 6）。

---

## 2. Run Now 一直停在 queued

**症狀**：按「Run Now（排入工作）」，訊息說已排入工作，但「最近執行」一直沒有新的 run；「工作與事件」頁該 job 永遠是 `queued`。

**重現**：只啟動 API、不啟動 worker：
```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app_factory --factory --host 127.0.0.1 --port 8001
```
（macOS/Linux：`.venv/bin/python`）。開 http://127.0.0.1:8001 按 Run Now。

**怎麼看 trace**
```bash
curl http://127.0.0.1:8001/api/health     # worker.alive = false
curl "http://127.0.0.1:8001/api/jobs?status=queued"
```
儀表板與工作頁也會顯示「worker 未執行」。

**原因與修復**：工作只放進 `jobs` 表，要有 worker process 去 `claim`。用 `python scripts/launcher.py start`（會一起啟動單一 worker），或另一個終端機執行 `cd backend && .venv/Scripts/python -m app.worker`。排好的 job 不會遺失，worker 一起來就會處理（單元 7）。若要立刻看結果，改按「立即執行並看結果」（`sync=true`，走同一個 service）。

---

## 3. 私訊「unknown」：不能重試、額度還留著

**症狀**：私訊投遞狀態是 `unknown`；工作狀態 `unknown`；按重試被拒（409 `needs_reconcile`）；用量頁「進行中保留」比平常多。

**重現**
1. 「留言與私訊模擬」把私訊失敗注入設為 `unknown`。
2. 換一個新的 event_id 注入事件，等 1–2 秒（worker），按「重新整理」。
3. （完成後）把注入調回 `none`。

**怎麼看 trace**
```bash
curl http://127.0.0.1:8000/api/deliveries?limit=5
curl "http://127.0.0.1:8000/api/jobs?status=unknown"
curl http://127.0.0.1:8000/api/usage        # balance.in_flight 增加
```
`usage_ledger` 裡該 operation 只有 `reserve`，沒有 `settle`/`release`。

**原因與修復**：模擬平台「逾時、不知道有沒有送出」。盲目重送可能重複發送，所以 `jobs.run_one` 把 `UnknownOutcome` 停在 unknown，`delivery.deliver` 也不會再做。到投遞紀錄按「確認已送出」（`sent`：settle 額度）或「確認未送出」（`not_sent`：改為 `failed_retryable`，可重新處理）。對應測試：`tests/test_delivery_jobs.py::test_unknown_outcome_stops_and_reconciles`。
