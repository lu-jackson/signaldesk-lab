# 設計決策記錄（只記錄實際採用的）

| # | 決策 | 理由 | 限制／代價 |
|---|---|---|---|
| 1 | 後端 FastAPI + 原生 `sqlite3`＋手寫參數化 SQL＋`.sql` migration | 規格指定；讓學習者直接看到表、FK、交易 | 沒有 ORM 的便利；SQL 字串要自己小心（全部參數化，欄位名不來自使用者輸入） |
| 2 | router／service／provider 三層；所有規則在 service | API、worker、agent 共用同一份規則，不會有人繞過審核 | 多一層函式呼叫 |
| 3 | 搜尋與分類分開；`evaluations` 欄位分存 included／relevant／intent／risk | 規格要求「搜尋結果不是已判定有意圖」；也方便單獨評估 | 一次執行要寫兩階段 |
| 4 | Demo 分類器用關鍵詞規則，且資料庫沒有任何標註欄位 | 無法「偷讀答案」；規則可讀可改 | 準確度有限（已量化並公布） |
| 5 | 核准綁 `content_hash`；編輯同時撤銷核准並退回 draft；送出時重新比對 | 雙保險：即使狀態欄被改，hash 不符仍不能送 | 小修改也要重新核准（刻意） |
| 6 | 全局去重鍵 `comment:{id}:{channel}`／`draft:{id}:public_reply`，不含 workflow version；同時是 `jobs.idempotency_key` 與 `delivery_dedup` PK | 改版本、重複事件、重複點擊都不會重送；兩層保護（enqueue 與投遞） | 想「重送同一則」必須是明確的新動作 |
| 7 | 投遞結果 5 態：pending／simulated_sent／failed_retryable／failed_terminal／unknown；unknown 不自動重試，需 reconcile | 結果不明時盲目重送可能重複發送 | 需要人工對帳（UI 有按鈕） |
| 8 | worker 為獨立 process＋SQLite jobs 表；claim 用 `BEGIN IMMEDIATE`；有副作用的工作 lease 過期 → unknown | 規格要求重啟可恢復且不重複副作用；不引入 Redis/Celery | 輪詢（1 秒）而非推送 |
| 9 | worker 單例以 DB heartbeat 保護，API 啟動不產生 worker | 規格：不得因 API 每次啟動重複產生 | heartbeat 15 秒 TTL；強殺後需等 TTL 才能再啟 |
| 10 | 帳本 reserve／settle／release，`UNIQUE(operation_id, entry_type)` | 重試不會多扣；失敗釋放；unknown 保持 reserved | available 由加總計算（無餘額欄位，避免不一致） |
| 11 | Agent：Demo 與 Live 共用同一個 loop，只替換 `agent_turn`；Demo 是 scripted planner | 讓學習者看到「同一迴圈、不同大腦」；測試不需金鑰 | Demo 規劃能力非常有限（已標示） |
| 12 | `prepare_draft` 為 agent 可直接執行的寫入（只建立 `draft`）；其餘寫入走 proposal | 規格 A15 要求助手產生「實際草稿」，A17 要求寫入走提案；草稿本身不外送、可拒絕，仍須人工核准＋送出 | 這是對兩條規格的一個折衷，若要更嚴格可把 prepare_draft 也改為提案 |
| 13 | 助手沒有任何送出／確認工具；確認只有 UI HTTP 端點 | 模型在文字裡說「已核准」不會有效力 | 未做 CSRF token（單使用者本機；有 Origin 檢查） |
| 14 | Live 失敗不降級：`NotConfigured`(503)／`DependencyError`(502) 直接顯示 | 規格 §3 | 使用者需明確切回 Demo |
| 15 | Anthropic client 與 Threads transport 可注入 | 測試不打付費／外部 API | — |
| 16 | 追蹤目的地只在建立時驗證（scheme、主機白名單、無帳密）；`/t/{token}` 不接受任何目標參數 | 不是 open redirect | 預設只允許 127.0.0.1／localhost，要外部網址需改環境變數 |
| 17 | 分析半開區間 `[from,to)`；無分母回 `null`；`has_data` 旗標 | 空值不偽裝成 0 | 前端 `to` 取下一個整分鐘以包含剛發生的事件 |
| 18 | 前端：React + 手寫 hash router、`useApi` hook，無狀態管理套件／UI 套件 | 學習負擔小；全部在 11 個頁面檔內 | 沒有快取與樂觀更新；`useApi` 重新整理時保留舊資料避免卸載元件 |
| 19 | 啟動器用 Python 標準庫（跨平台），ps1/sh 只是薄包裝 | 不假設 make/uv/pnpm | 需先有 Python 才能啟動 |
| 20 | 依賴鎖版：後端 `requirements.lock.txt`（pip freeze）、前端 `package-lock.json` | 可重現；版本來自實際安裝並測過的組合（FastAPI 0.163.1、Pydantic 2.14.3、anthropic 2.8.0、Vite 8.3.8、React 19.3.1、TypeScript 7.0.2） | 版本很新，升級時要重測 |
| 21 | 測試以臨時 DB＋可凍結時鐘；E2E 啟動獨立 server | 不破壞使用者 Demo DB；時間相關邏輯可確定性測試 | E2E 較慢（約 14 秒） |
