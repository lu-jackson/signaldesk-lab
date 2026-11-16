# 程式地圖：先看這 12 個檔案（依建議閱讀順序）

| # | 檔案 | 責任 | 為什麼先看 |
|---|---|---|---|
| 1 | `backend/app/migrations/001_init.sql` | 全部資料表與約束 | 先懂資料長什麼樣，其他都是在操作它 |
| 2 | `backend/app/db.py` | 連線設定（FK/WAL）、`tx` 短交易、分頁 helper | 所有 service 的共同基礎 |
| 3 | `backend/app/services/pipeline.py` | 搜尋→分類→run 的主流程 | 流程一的主幹，`execute_run` 一個函式串起全部 |
| 4 | `backend/app/providers/ai_demo.py` | Demo 規則分類、模板草稿、scripted planner | 看到「不是 LLM」的具體樣子 |
| 5 | `backend/app/services/drafts.py` | 草稿、核准（hash）、送出前檢查 | 最重要的人工閘門 |
| 6 | `backend/app/services/delivery.py` | 全局去重、投遞狀態機、reconcile、與帳本互動 | 「副作用只發生一次」的核心 |
| 7 | `backend/app/services/jobs.py` + `worker.py` | 工作佇列、lease、retry、排程 tick | 流程二與重啟恢復 |
| 8 | `backend/app/services/automations.py` | 留言規則、事件去重、channel 工作 | 流程二的入口與處理 |
| 9 | `backend/app/services/agent.py` | agent loop、工具白名單、proposal | 真正的 tool-use 迴圈 |
| 10 | `backend/app/providers/ai_anthropic.py` | Live adapter（注入 client、JSON 修復） | 對照 #4，看 Demo 與 Live 的界線 |
| 11 | `backend/tests/test_delivery_jobs.py` | 失敗注入、unknown、lease、排程的測試 | 測試就是最好的行為說明書 |
| 12 | `frontend/src/api.ts` + `pages/Drafts.tsx` | 前端與後端的連接方式與一個完整頁面 | 看畫面如何呈現 loading/error/retry 與核准狀態 |

次要但值得知道：`routers/*.py`（HTTP 薄層）、`services/ledger.py`（帳本）、`services/tracking.py`（連結與分析）、`services/leads.py`、`seed.py`、`eval/evaluate.py`、`scripts/launcher.py`。

閱讀訣竅：從 UI 一個按鈕出發，用 `Ctrl+F` 在前端找它呼叫的 `/api/...`，再到 `routers/` 找對應函式，最後進 `services/`；不要從檔案列表由上往下讀。
