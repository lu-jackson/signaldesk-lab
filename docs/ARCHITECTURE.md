# 最終架構

## 目錄
```
signaldesk-lab/
├─ backend/
│  ├─ app/
│  │  ├─ main.py            create_app()：路由、錯誤處理、Origin 守衛、供應 frontend/dist
│  │  ├─ config.py clock.py db.py errors.py deps.py schemas.py
│  │  ├─ migrations/001_init.sql
│  │  ├─ seed.py            固定 seed 的合成資料；reset-demo
│  │  ├─ worker.py          獨立 worker process + schedule_tick
│  │  ├─ routers/           core / content / ops / agent  （HTTP 薄層，無商業邏輯）
│  │  ├─ services/          pipeline, drafts, delivery, jobs, automations, leads, tracking, ledger, agent, catalog, settings（所有規則在這裡）
│  │  └─ providers/         base（介面）, ai_demo, ai_anthropic, social（Demo/Threads 唯讀/模擬投遞）
│  ├─ tests/ (91)   eval/（36 筆人工標註 + 評估腳本）
│  └─ requirements.txt / requirements.lock.txt
├─ frontend/src/            React 19 + TS：api.ts（fetch + useApi）、ui.tsx、App.tsx、pages/*（11 頁）
├─ e2e/                     Playwright（pytest）
├─ scripts/                 launcher.py、setup/dev（ps1/sh）、gen_api_doc.py
└─ docs/
```
**分層規則**：router 只做 HTTP 轉換；`services/*` 持有所有商業規則；API、worker、agent 呼叫同一批 service，所以「核准才能送」「去重」「額度」只寫一次。前端不碰 DB；agent 沒有任何繞過 service 的路徑。

## 資料模型（`001_init.sql`）
| 區塊 | 表 |
|---|---|
| 品牌／帳號／專案 | `brands`＋`brand_versions`（每次改版新增一列，舊版保留）、`social_accounts`（CHECK handle 必須 `demo_` 開頭）、`projects`（CHECK mode／天數） |
| 資料與判斷 | `source_posts`、`comments`、`runs`（保存參數與品牌版本）、`evaluations`（搜尋納入/排除原因＋分類結果分欄儲存） |
| 草稿與投遞 | `drafts`（content_hash、revision、brand_version）、`approvals`（綁 hash、可撤銷）、`delivery_attempts`、`delivery_dedup`（全局去重鍵 PK） |
| 自動化與事件 | `automation_rules`（version）、`events`（`event_id` UNIQUE） |
| 工作 | `jobs`（status CHECK、lease_until、idempotency_key UNIQUE、side_effect） |
| 名單 | `lead_lists`、`leads`（UNIQUE(platform,handle)）、`lead_sources`、`lead_activity` |
| 追蹤與分析 | `tracking_links`、`click_events`、`engagement_snapshots`（合成） |
| 帳本 | `usage_ledger`（UNIQUE(operation_id, entry_type)，append-only） |
| 助手 | `agent_sessions`、`agent_messages`、`tool_calls`、`action_proposals` |
| 其他 | `settings`、`idempotency_keys`、`schema_migrations` |

每個 connection：`foreign_keys=ON`、`busy_timeout`、WAL（`db.connect`）。寫入用 `db.tx()` = `BEGIN IMMEDIATE` 的短交易；AI／模擬投遞呼叫一律在交易外。

## 兩條主要資料流

**流程一：搜尋到模擬送出**
`Projects 頁 → POST /api/projects/{id}/run-now → pipeline.execute_run`
1. `search_candidates`：provider 以關鍵字＋半開時間窗 `[now-days, now)` 查貼文，再套必要／排除條件，每筆附納入／排除原因與原文證據。
2. `record_candidates` 寫 `evaluations`（此時**尚無**意圖）。
3. `classify_evaluation`：reserve 額度 → `AIProvider.classify`（Demo 規則或 Live）→ 寫入 intent/risk/reason/evidence → settle（失敗 release 並記錄 `classify_error`，不降級）。
4. `drafts.create_draft`（只對 relevant＋seeking＋非 prompt_injection）；高/中風險標 `requires_human`。
5. 人在草稿頁編輯／核准（`approvals` 綁 hash）→ `simulate_send` → `delivery.deliver`：dedup 鍵、reserve、模擬投遞、settle/release。

**流程二：事件到名單／分析**
`POST /api/simulator/events → automations.ingest_event`（`events.event_id` UNIQUE 去重 → 寫 comment → enqueue `process_event`）
→ worker `handle_event`（找符合規則）→ 每個 channel enqueue `comment_channel`（idempotency_key `comment:{id}:{channel}`）→ `handle_channel` → `delivery.deliver`（`delivery_dedup` 同鍵）→ 公開回覆成功時 `leads.upsert_lead` → 追蹤連結點擊 `/t/{token}` → `tracking.summary`。

## Worker 與工作佇列（`services/jobs.py`、`worker.py`）
- `claim`：同一個 `BEGIN IMMEDIATE` 交易內 SELECT 最舊的 queued、UPDATE 為 running 並設 `lease_until`。
- `recover_expired`：lease 過期的 running 工作——無副作用 → 回 queued；`side_effect=1`（送出類）→ **unknown**，不盲目重跑。
- 重試：`RetryableError` → 指數 backoff（5s·2^(n-1)），到 `max_attempts` → failed；`UnknownOutcome` → unknown；`TerminalError` → failed 且不重試。
- 排程：`worker.schedule_tick` 以 `(project, next_run_at)` 作 idempotency key enqueue，再前移 `next_run_at`；改排程不會額外 enqueue。UTC 運算，UI 時區選單顯示 Europe/London 等。
- 單例：`settings.worker_heartbeat`；15 秒內有別的 pid → 拒絕啟動。API 啟動不產生 worker。

## Agent loop（`services/agent.py`）
```
使用者訊息 → [loop ≤ 8 回合]
   ai.agent_turn(messages, TOOLS)       # Demo: scripted planner；Live: Anthropic messages.create(tools=…)
   ├─ 無 tool_use → 結束(completed)
   └─ 逐一處理每個 tool_use（保留 id）：白名單檢查 → Pydantic 驗參 → run_tool → tool_result(is_error?)
      （總工具呼叫 ≤ 12；超額者回 error tool_result 並以 limit_reached 結束；cancel 後不再執行新工具）
   → 所有 tool_result 以同一則 user 訊息回傳 → 下一回合
```
- 8 個唯讀／低風險工具；沒有 shell/HTTP/SQL/檔案/送出工具。`prepare_draft` 只建立 `draft` 狀態。
- 寫入只能 `propose_lead_update` → `action_proposals(pending)`；`/api/agent/proposals/{id}/confirm` 是給 UI 的 HTTP 端點，agent 工具集沒有它。模型文字說「已核准」沒有任何效力。
- `agent_messages` 存完整 content blocks（含 tool_use id / tool_result）；`tool_calls` 存脫敏參數與輸出摘要（`redact()` 遮掉 key 樣式字串）。不保存模型隱藏思考。
- **確定性 pipeline ≠ 自主 agent ≠ Demo scripted planner**：流程一二是固定程式；Demo 助手是依規則挑工具的腳本；只有 `AnthropicAI.agent_turn` 才是真的 LLM tool-use。

## 模式與信任邊界
`settings` 表三個獨立值：`social_source`、`ai_provider`、`delivery_mode`（只能 simulation）。Secret 只從環境變數讀（`config.py`），前端只拿 `*_configured` 布林。寫入請求的 `Origin` 不在允許清單 → 403。追蹤連結目的地於建立時驗證（scheme/host 白名單/無帳密），`/t/{token}` 不接受任何目標參數。

## 已做／未做
已做：規格 §4 全部模組、§5 agent、§6 資料模型、§7 API、§8 adapter、§9 合成資料與 eval、§10 M0–M5。
未做（規格明列「不做」或屬外部邊界）：真實發送／付款／部署／多租戶／OAuth 審核／影片／網紅市集／全網爬取；Anthropic Live 與 Threads 的真實連線驗證（見 KNOWN_LIMITATIONS）。
