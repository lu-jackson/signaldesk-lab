# SignalDesk Lab 開發規格

版本：1.0｜2026-11-16｜用途：個人案例分析、完整開發後自學。

## 1. 目標與範圍

交付一個可在本機運行、資料可持久化、有前後端、可完整走完情境的應用程式。不是商用平台複製，也不是對任何企業內部實作的推測。

**必做：**品牌設定、合成社群帳號、追蹤專案、貼文搜尋、意圖與風險篩選、草稿與審核、模擬投遞、留言轉私訊模擬、名單、連結事件、分析、工作佇列、AI 助手工具介面、學習文件。

**可配置但不阻擋完成：**Anthropic Live AI；Threads 唯讀搜尋 adapter。前者提供可執行程式碼與 mocked contract tests；後者提供依官方文件實作的連接流程和清楚錯誤，但無 token 時不聲稱 live 驗證。

**不做：**真實自動留言／DM、付款、公司化帳務、公開部署、多人租戶、正式 OAuth 審核、影片生成／剪輯、網紅市集、全網完整爬取、保證成交的預測模型。

## 2. 技術選擇與環境

| 層 | 指定方向 | 原因 |
|---|---|---|
| 前端 | React + TypeScript + Vite，繁體中文 UI | 分開練習 UI、狀態與 API。 |
| 後端 | Python 3.11+、FastAPI、Pydantic | 貼近使用者 Python／ML 學習。 |
| DB | Python sqlite3、參數化 SQL、明確 migrations | 無需額外 DB server，能學資料關係與 transaction。 |
| 背景工作 | SQLite 持久化工作表＋單獨 Python worker process | 重啟後可觀察和恢復。 |
| 程式測試 | pytest + HTTP client；前端 typecheck；Playwright 關鍵流程 | 測真正行為與瀏覽器操作。 |
| LLM | Anthropic SDK 的獨立 adapter | 用工具 schema 實作可檢視的 agent loop。 |
| 啟動 | setup／dev 的 PowerShell 與 shell 腳本，或等效跨平台 Python launcher | Windows 優先，也可於 macOS／Linux 使用。 |

Node 請選與實際 Vite 版本相容的 LTS；前置檢查必須讀出版本並提供錯誤提示。不要假設使用者有 Docker、uv、pnpm 或 make。預設 Python venv + pip、npm 即可。依賴首次安裝需要網路，安裝完成後 Demo 運行不需外部服務。

開發期以 Vite proxy 導向後端；build 後讓 FastAPI 供應前端靜態檔，使完成版只需一個 localhost 網址。API 保留 `/api`，健康檢查 `/api/health`。worker 不得因 API 每次啟動而重複產生。

## 3. 模式與信任邊界

分開儲存三個設定，不能一個 LIVE 開關全打開：

- `SOCIAL_SOURCE=demo|threads_readonly`。
- `AI_PROVIDER=demo|anthropic`。
- `DELIVERY_MODE=simulation`：此次只能為 simulation。

Demo 顯示規則／模板來源；Live AI 顯示模型、時間及實際 token 計量（若供應商有回傳）。Demo 耗用顯示模擬單位，不換算成真實 token 或帳單。

當 Live AI 失敗，不得靜默切換 Demo。顯示錯誤，允許使用者明確改模式。設定存 DB 的可見欄位不得存 secret；API key 從後端 .env 讀取，前端只看 configured 布林值。

本機單使用者。限制 localhost、預設拒絕非預期 Origin 的寫入、CORS 僅實際開發 origin；不要把「無登入」設計當作可公開部署的系統。

## 4. UI 與模組

風格：清楚的研究儀表板，側邊導覽、白底或深淺切換、適量色彩，不要大量裝飾。所有按鈕有 loading、empty、error 與重試狀態。桌面優先，平板與小螢幕可操作；避免只能滑鼠拖曳才能完成工作。

### 4.1 Dashboard

顯示目前模式、進行中工作、待審草稿、有效商機、風險警報、模擬投遞結果與最近執行。每個指標可點到清單；顯示分母、期間與更新時間。不得把合成數據當真實社群成果。

### 4.2 品牌與帳號

品牌 CRUD：名稱、介紹、產品、受眾、服務範圍、語氣、FAQ、可確認事實、不可承諾事項、CTA。品牌變動增加 version。既有草稿保留原版本並顯示「品牌設定已更新」，需重新生成或再核准。

帳號 Demo 只用 `demo_*`，分 Threads／X／Instagram／Facebook。帳號和品牌用下拉選擇連接。不得使用真實人的照片、handle 或貼文。

### 4.3 主題專案與搜尋

專案欄位：品牌、帳號、目的、關鍵字、必要／排除條件、時間範圍、Manual Review／Observe Only／Auto Simulate、每日模擬上限及排程開關。

Demo 搜尋用關鍵字和時間查 SQLite fixture，不假裝向量語意搜尋。支援熱門／最新排序。AI 分類另外執行，不能把搜尋結果當成已判定有意圖。呈現 inclusion／exclusion 原因及 evidence snippet。

每次執行保存 run、參數、品牌版本、候選數、分類及草稿數、錯誤；可重新打開結果。Auto Simulate 只會送到本機模擬平台。

### 4.4 意圖、風險與草稿

分類分開存：relevant、intent（seeking/advice/promotion/complaint/other）、risk（low/medium/high）、reason、evidence。Demo 用可讀規則，不使用 fixture 正確標籤當輸入，規則不可偽裝成機率。

Live AI 輸出經 Pydantic 驗證；不合規結果最多一次格式修復，仍失敗即記錄失敗。模型建議分數不是已校準 confidence。外部貼文一律當不可信資料，不允許其中的指令操作工具。

草稿根據原文、品牌事實、FAQ 與限制生成。不得捏造優惠、價格、保證結果或使用經驗。UI 可改稿、核准、拒絕、模擬送出；核准綁定草稿內容 hash／版本，修改後核准失效。風險高的貼文不走 Auto Simulate，送人工審核。

### 4.5 留言與私訊模擬

選 Demo 自有貼文，設定 contains 關鍵字（大小寫不敏感，OR）、公開回覆模板與最多三個連結。明確區分「既有留言一次處理」和「新事件觸發」。預覽不能送出。

每個 comment＋workflow version＋channel 有結果紀錄；同一留言不得因 workflow 改版本而重複送同 channel，需另有全局去重鍵。公開回覆與 DM 成敗分開，收到事件和訊息已讀分開。Demo 可注入：成功、權限失效、rate limit、終局失敗、結果未知。

### 4.6 名單與 PR

名單記錄平台、handle、來源貼文、理由、狀態、備註及歷史。以平台＋handle 去重，保留多來源；狀態 New／Qualified／Ignored／Converted 可編輯。Converted 僅人工分類，畫面明示不代表訂單。

完整 JSON 匯出包含關聯與歷史；CSV 包含所有匹配資料而不只已載入頁面，欄位有說明。單元測試要覆蓋分頁匯出與 CSV formula injection。PR 視圖以 risk 分流，保持原文與理由；不宣稱預測危機。

### 4.7 追蹤連結與分析

建立本機 tracking link，僅映射到預先設定且驗證的 http/https 目的網址，request 不能任意指定 redirect target。測試預設導向本機 Demo landing page。

記錄 click、is_bot、時間與 session pseudonym。只用隨機 session cookie 做估算 unique visits，不做裝置指紋；Demo 國家／裝置若是 fixture 必須標合成。沒有資料時不得瞎填地點。

整體與圖表篩選一致。顯示 API accepted／simulated sent、click、estimated unique；不提供假的已讀／成交。可加入使用合成 engagement snapshots 的貼文監測圖；明示為固定 seed 模擬，非即時平台資料。

### 4.8 工作與事件

Jobs UI：queued/running/succeeded/failed/cancelled/unknown，嘗試數、錯誤、時間、下一次執行。SQLite transaction 原子 claim，lease expiry、有限重試與指數 backoff。重啟不能把外部結果不明的送出盲目重跑。

Webhook simulator 先落地 event_id 去重再排工作，重複事件回相同接受結果。此路徑僅本機測試；如實作外部 webhook handler，必須驗簽並具獨立開關，不能和無簽章 simulator 混用。

排程儲存 next_run_at、interval_seconds、enabled；以 UTC 運算，UI 可顯示 Europe/London；修改排程不能雙重 enqueue。使用者可立即 Run Now，無需等待排程驗收。取消工作不撤回已完成副作用。

### 4.9 使用量帳本

本機虛擬 units，用於學習計量，不使用研究公司的扣點。建立自己的示例費率設定，明示無現金價值。帳本 append-only、operation_id 唯一，區分 reserve/settle/release，不因重試重複扣款。

## 5. 真正的 Agent 與 Demo 模擬

**確定性 pipeline 不等於自主 agent。** Demo Assistant 是 scripted planner，支援固定範圍自然語句並顯示「模擬規劃」。Live Anthropic Assistant 必須實作真正 tool-use round trip：

使用者目標 → 模型決定 tool_use → 後端驗參數／權限 → 執行工具 → tool_result → 模型繼續或結束。

工具至少包含：list_projects、search_demo_posts、get_brand、classify_posts、prepare_draft、list_leads、propose_lead_update、get_run_status。不要給 shell、任意 HTTP、任意 SQL 或檔案工具。

Run trace 保存 tool name、脫敏參數、輸出摘要、狀態與時間；不要求或保存模型隱藏思考。最大 8 個模型回合、最多 12 次工具呼叫、明確 timeout；取消後不繼續新工具。多 tool_use block 需逐個正確回 tool_result，同時保留 call id；工具失敗回工具錯誤，不編造成功。

所有修改／發送先形成 action proposal。UI 確認後由同一 domain service 驗證並執行，不能因模型在下一輪說「已核准」就放行。GET 工具可直接執行。Demo 手動核准及 Auto Simulate 由獨立專案政策控制，不允許模型改政策。

驗收例句：「搜尋最近七天需要台北租屋協助的 Demo 貼文，排除仲介廣告，替前三篇準備回覆，但不要送出。」必須有可檢查 trace、實際 DB 草稿、零投遞。數量不足時回報實際數量。

## 6. 最小資料模型

表名可調整，但功能與約束不可省略：brands + brand_versions、social_accounts、projects、source_posts、runs、evaluations、drafts、approvals、automation_rules、events、jobs、delivery_attempts、delivery_dedup、lead_lists、leads、lead_sources、lead_activity、tracking_links、click_events、usage_ledger、agent_sessions、agent_messages、tool_calls、action_proposals、schema_migrations。

每個表有穩定 id、UTC timestamps；FK、UNIQUE、CHECK 及必要 index。sqlite 每 connection 啟用 foreign_keys；WAL、busy_timeout、短交易，LLM／網路請求不要放在持鎖交易內。

所有 service 由 API、worker、agent 共用。前端不能直接操作 DB，agent 不能繞過同一審核規則。

## 7. API 合約

以 FastAPI OpenAPI 為真實來源，另產出 docs/API.md。路徑可在一致性下調整：

| 範圍 | 必要操作 |
|---|---|
| `/api/brands`、`/api/accounts` | 查詢／新增／更新品牌與 Demo 帳號。 |
| `/api/projects` | CRUD、啟停、run-now、runs。 |
| `/api/posts`、`/api/evaluations` | 搜尋、分頁、評估。 |
| `/api/drafts` | 生成／編輯／核准／拒絕／simulate-send。 |
| `/api/automations`、`/api/simulator/events` | 設定規則與注入事件。 |
| `/api/leads`、`/api/lists` | CRUD、來源／歷史、CSV／JSON export。 |
| `/api/jobs` | 狀態／取消／可安全的 retry。 |
| `/api/agent/sessions` | 建會話、送訊息、trace、proposal 確認。 |
| `/api/analytics`、`/t/{token}` | 期間彙總及本機追蹤 redirect。 |
| `/api/settings`、`/api/health` | 非敏感設定、能力狀態、健康。 |

寫入用 request id 或 Idempotency-Key；明確區分 400、404、409、422 及依賴失敗。對列表使用一致分頁。後端時間篩選用半開區間；前端空值與 loading 不顯示成零。

## 8. 外部 Adapter

### AI

`AIProvider`：classify、draft、agent_turn；Demo 和 Anthropic 共用 schema。Anthropic 用官方 SDK，model ID 從 `ANTHROPIC_MODEL` 讀，沒配置就不發請求。測試 mock responses 包含 tool_use、text、error、invalid JSON、multiple tools、limit exhaustion。不要為了通過測試真正呼叫收費 API。

### 社群

`SocialProvider`：search_posts、list_comments、simulate_delivery 等責任分開。Demo 實作完整；ThreadsReadonlyProvider 使用官方 endpoint、驗 token、處理 401/403/429、分頁、時間及無資料。拒絕 write methods，不能讓 adapter 繼承後意外可送出。

無權限的外部能力標「未配置／未實測」，不偽裝成持續開發中的空白主功能。核心 Demo 必須完成。不要加入爬蟲或用公開 token 假裝可以搜尋全站。

## 9. 合成資料與可重現性

至少 3 個虛構品牌（租屋顧問、課程工作室、甜點店）、4 平台 Demo 帳號、120 篇合成貼文、80 則合成留言，含需求、廣告、已解決、抱怨、諷刺、無關及惡意指令。

seed 固定 random seed，但時間相對於可注入 clock；同一天重新 seed 結果一致，過期資料不會讓「最近七天」全變空。seed 不可在正常啟動時清空使用者修改；reset-demo 須明確警告並僅重設 Demo DB。

另有至少 30 筆人工標註 eval fixtures，與 Demo runtime 規則分離；報告分類 precision／recall 或 confusion matrix，分母及零分母清楚。這些是合成資料評估，不宣稱真實商業有效性。

## 10. 里程碑

1. M0：檢查環境、選版、目錄、schema、fixtures、setup/dev scripts。
2. M1：品牌→搜尋→分類→草稿→核准→模擬送出，DB 與 UI 端到端。
3. M2：留言事件、背景工作、去重、失敗注入、名單與匯出。
4. M3：追蹤連結、分析、PR、排程及使用量帳本。
5. M4：Demo assistant、真正 Anthropic tool-use adapter、trace、proposal gate、Threads 唯讀 adapter。
6. M5：回歸測試、瀏覽器驗收、修正、文件與教學。

每階段可自主修正架構，但不能把未完成的重要模組移到 future work 來宣稱全數完成。環境缺外部憑證是已知可配置邊界，不阻擋核心交付。

## 11. 官方參考（查閱 2026-11-16）

- FastAPI：https://fastapi.tiangolo.com/
- Vite：https://vite.dev/guide/
- Python sqlite3：https://docs.python.org/3/library/sqlite3.html
- Anthropic tool use：https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- Threads search：https://developers.facebook.com/documentation/threads/keyword-search

以上是技術參考，不涉及任何研究公司的來源。執行開發時仍需依實際安裝版本核對介面。
