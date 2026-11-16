# API 文件

> 本檔由 `scripts/gen_api_doc.py` 依 FastAPI OpenAPI 自動產生（真實來源是程式碼；執行中的服務也可看 `/docs` 與 `/openapi.json`）。
> 所有 JSON 錯誤格式一致：`{"error": {"code": "...", "message": "..."}}`。

## 通用約定

| 狀態碼 | 意義 |
|---|---|
| 400 | 輸入語意錯誤（例如危險的追蹤網址、時間區間顛倒、設定值不合法） |
| 404 | 資源不存在 |
| 409 | 狀態衝突（未核准不可送出、重複確認提案、額度不足、唯一性衝突） |
| 422 | 請求 schema 不符（Pydantic 驗證；含無效 enum） |
| 403 | 寫入請求帶了不允許的 Origin |
| 502 | 外部依賴失敗（Live AI / Threads 回應錯誤） |
| 503 | 能力未配置（例如選了 Anthropic 但沒有 key/model；不會降級成 Demo） |

- **分頁**：`?page=1&page_size=20` → `{items, total, page, page_size}`（page_size 上限 200）。
- **Idempotency-Key**：`run-now`、`simulate-send`、助手訊息接受 `Idempotency-Key` header；同 key 重送回傳第一次的結果。
- **時間**：一律 UTC `YYYY-MM-DDTHH:MM:SSZ`；區間為半開 `[from, to)`。
- **寫入 Origin 檢查**：瀏覽器寫入請求若 `Origin` 不在允許清單（預設 127.0.0.1/localhost 的 8000、5173）→ 403。

## 範例

```bash
# 立即同步執行專案（搜尋→分類→草稿）
curl -X POST "http://127.0.0.1:8000/api/projects/proj_rent/run-now?sync=true"
# 核准與模擬送出（沒有有效核准 → 409 approval_required）
curl -X POST http://127.0.0.1:8000/api/drafts/<draft_id>/approve
curl -X POST http://127.0.0.1:8000/api/drafts/<draft_id>/simulate-send -H "Idempotency-Key: demo-1"
# 注入留言事件（重複 event_id → duplicate:true）
curl -X POST http://127.0.0.1:8000/api/simulator/events -H "Content-Type: application/json" \
  -d '{"event_id":"e1","post_id":"own_rent_1","author_handle":"demo_tester","text":"請給我清單"}'
```

## 端點


### accounts

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/accounts` | — | — | 200 | Accounts |
| `POST` | `/api/accounts` | AccountIn | — | 201, 422 | Account Create |
| `PUT` | `/api/accounts/{account_id}` | AccountIn | — | 200, 422 | Account Update |

### agent

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/agent/tools` | — | — | 200 | Tools |
| `GET` | `/api/agent/sessions` | — | — | 200 | Sessions |
| `POST` | `/api/agent/sessions` | SessionIn | — | 201, 422 | Session Create |
| `GET` | `/api/agent/sessions/{sid}` | — | — | 200, 422 | Session Get |
| `POST` | `/api/agent/sessions/{sid}/messages` | AgentMessageIn | `idempotency-key` | 200, 422 | Session Message |
| `POST` | `/api/agent/sessions/{sid}/cancel` | — | — | 200, 422 | Session Cancel |
| `GET` | `/api/agent/proposals` | — | `status` | 200, 422 | Proposals |
| `POST` | `/api/agent/proposals/{pid}/confirm` | — | — | 200, 422 | Proposal Confirm |
| `POST` | `/api/agent/proposals/{pid}/reject` | — | — | 200, 422 | Proposal Reject |

### analytics

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/analytics/summary` | — | `from`, `to`, `link_id` | 200, 422 | Analytics |
| `GET` | `/api/analytics/engagement` | — | `from`, `to` | 200, 422 | Engagement |

### automations

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/automations` | — | — | 200 | Rules |
| `POST` | `/api/automations` | RuleIn | — | 201, 422 | Rule Create |
| `PUT` | `/api/automations/{rid}` | RuleIn | — | 200, 422 | Rule Update |
| `POST` | `/api/automations/{rid}/preview` | — | — | 200, 422 | Rule Preview |
| `POST` | `/api/automations/{rid}/process-existing` | — | — | 202, 422 | Rule Process Existing |

### brands

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/brands` | — | — | 200 | Brands |
| `POST` | `/api/brands` | BrandIn | — | 201, 422 | Brand Create |
| `GET` | `/api/brands/{brand_id}` | — | `version` | 200, 422 | Brand Get |
| `PUT` | `/api/brands/{brand_id}` | BrandIn | — | 200, 422 | Brand Update |

### dashboard

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/dashboard` | — | — | 200 | Dashboard |

### deliveries

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/deliveries` | — | `limit` | 200, 422 | Deliveries |
| `POST` | `/api/deliveries/{aid}/reconcile` | — | `resolution`* | 200, 422 | Reconcile |

### drafts

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/drafts` | — | `status`, `project_id`, `page`, `page_size` | 200, 422 | Drafts List |
| `POST` | `/api/drafts` | DraftGenerate | — | 201, 422 | Draft Generate |
| `GET` | `/api/drafts/{did}` | — | — | 200, 422 | Draft Get |
| `PUT` | `/api/drafts/{did}` | DraftEdit | — | 200, 422 | Draft Edit |
| `POST` | `/api/drafts/{did}/approve` | — | — | 200, 422 | Draft Approve |
| `POST` | `/api/drafts/{did}/reject` | — | — | 200, 422 | Draft Reject |
| `POST` | `/api/drafts/{did}/regenerate` | — | — | 201, 422 | Draft Regenerate |
| `POST` | `/api/drafts/{did}/simulate-send` | — | `idempotency-key` | 200, 422 | Draft Send |

### evaluations

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/evaluations` | — | `risk`, `intent`, `project_id`, `page`, `page_size` | 200, 422 | Evaluations |

### events

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/events` | — | `page`, `page_size` | 200, 422 | Events |

### health

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/health` | — | — | 200 | Health |

### jobs

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/jobs` | — | `status`, `page`, `page_size` | 200, 422 | Jobs List |
| `POST` | `/api/jobs/{jid}/cancel` | — | — | 200, 422 | Job Cancel |
| `POST` | `/api/jobs/{jid}/retry` | — | — | 200, 422 | Job Retry |

### leads

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/leads` | — | `status`, `q`, `page`, `page_size` | 200, 422 | Leads List |
| `POST` | `/api/leads` | LeadIn | — | 201, 422 | Lead Add |
| `GET` | `/api/leads/export.csv` | — | `status`, `q` | 200, 422 | Leads Csv |
| `GET` | `/api/leads/export.json` | — | `status`, `q` | 200, 422 | Leads Json |
| `GET` | `/api/leads/{lid}` | — | — | 200, 422 | Lead Get |
| `PATCH` | `/api/leads/{lid}` | LeadPatch | — | 200, 422 | Lead Patch |

### links

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/links` | — | — | 200 | Links |
| `POST` | `/api/links` | LinkIn | — | 201, 422 | Link Create |

### lists

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/lists` | — | — | 200 | Lists |

### other

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/t/{token}` | — | — | 200, 422 | Track |
| `GET` | `/demo-landing` | — | — | 200 | Landing |

### posts

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/posts` | — | `q`, `sort`, `page`, `page_size` | 200, 422 | Posts |
| `GET` | `/api/posts/own` | — | — | 200 | Own Posts |
| `GET` | `/api/posts/{post_id}/comments` | — | `page`, `page_size` | 200, 422 | Post Comments |

### projects

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/projects` | — | — | 200 | Projects |
| `POST` | `/api/projects` | ProjectIn | — | 201, 422 | Project Create |
| `GET` | `/api/projects/{pid}` | — | — | 200, 422 | Project Get |
| `PUT` | `/api/projects/{pid}` | ProjectIn | — | 200, 422 | Project Update |
| `DELETE` | `/api/projects/{pid}` | — | — | 204, 422 | Project Delete |
| `POST` | `/api/projects/{pid}/enable` | — | `enabled` | 200, 422 | Project Enable |
| `POST` | `/api/projects/{pid}/run-now` | — | `sync`, `idempotency-key` | 202, 422 | Project Run Now |
| `GET` | `/api/projects/{pid}/runs` | — | `page`, `page_size` | 200, 422 | Project Runs |

### runs

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/runs/{run_id}` | — | — | 200, 422 | Run Get |
| `GET` | `/api/runs/{run_id}/results` | — | `page`, `page_size`, `included` | 200, 422 | Run Results |

### settings

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/settings` | — | — | 200 | Get Settings |
| `PATCH` | `/api/settings` | SettingsPatch | — | 200, 422 | Patch Settings |

### simulator

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `POST` | `/api/simulator/events` | CommentEventIn | — | 202, 422 | Sim Event |
| `POST` | `/api/simulator/inject` | InjectIn | — | 200, 422 | Sim Inject |

### usage

| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |
|---|---|---|---|---|---|
| `GET` | `/api/usage` | — | — | 200 | Usage |

## Schemas

### AccountIn

| 欄位 | 型別 | 必填 |
|---|---|---|
| `platform` | enum(threads/x/instagram/facebook) | 是 |
| `handle` | string | 是 |
| `display_name` | string | 是 |
| `brand_id` | string|null | 否 |

### AgentMessageIn

| 欄位 | 型別 | 必填 |
|---|---|---|
| `content` | string | 是 |

### BrandData

| 欄位 | 型別 | 必填 |
|---|---|---|
| `intro` | string | 否 |
| `products` | array | 否 |
| `audience` | string | 否 |
| `service_area` | string | 否 |
| `tone` | string | 否 |
| `faq` | array | 否 |
| `facts` | array | 否 |
| `forbidden` | array | 否 |
| `cta` | string | 否 |

### BrandIn

| 欄位 | 型別 | 必填 |
|---|---|---|
| `name` | string | 是 |
| `data` | BrandData | 否 |

### CommentEventIn

| 欄位 | 型別 | 必填 |
|---|---|---|
| `event_id` | string | 是 |
| `post_id` | string | 是 |
| `author_handle` | string | 是 |
| `text` | string | 是 |

### DraftEdit

| 欄位 | 型別 | 必填 |
|---|---|---|
| `body` | string | 是 |

### DraftGenerate

| 欄位 | 型別 | 必填 |
|---|---|---|
| `project_id` | string | 是 |
| `post_id` | string | 是 |

### InjectIn

| 欄位 | 型別 | 必填 |
|---|---|---|
| `channel` | enum(public_reply/dm/draft_reply) | 是 |
| `outcome` | enum(none/success/permission_revoked/rate_limit/terminal_failure/unknown) | 是 |

### LeadIn

| 欄位 | 型別 | 必填 |
|---|---|---|
| `platform` | enum(threads/x/instagram/facebook) | 是 |
| `handle` | string | 是 |
| `post_id` | string|null | 否 |
| `reason` | string | 是 |

### LeadPatch

| 欄位 | 型別 | 必填 |
|---|---|---|
| `status` | string|null | 否 |
| `note` | string|null | 否 |

### LinkIn

| 欄位 | 型別 | 必填 |
|---|---|---|
| `label` | string | 是 |
| `destination` | string | 是 |

### ProjectIn

| 欄位 | 型別 | 必填 |
|---|---|---|
| `name` | string | 是 |
| `brand_id` | string | 是 |
| `account_id` | string | 是 |
| `purpose` | string | 否 |
| `keywords` | array | 是 |
| `must_terms` | array | 否 |
| `exclude_terms` | array | 否 |
| `window_days` | integer | 否 |
| `mode` | enum(manual_review/observe_only/auto_simulate) | 否 |
| `daily_limit` | integer | 否 |
| `schedule_enabled` | boolean | 否 |
| `interval_seconds` | integer | 否 |
| `enabled` | boolean | 否 |

### RuleIn

| 欄位 | 型別 | 必填 |
|---|---|---|
| `name` | string | 是 |
| `post_id` | string | 是 |
| `keywords` | array | 是 |
| `reply_template` | string | 是 |
| `send_dm` | boolean | 否 |
| `dm_template` | string | 否 |
| `links` | array | 否 |
| `enabled` | boolean | 否 |

### SessionIn

| 欄位 | 型別 | 必填 |
|---|---|---|
| `title` | string | 否 |

### SettingsPatch

| 欄位 | 型別 | 必填 |
|---|---|---|
| `social_source` | string|null | 否 |
| `ai_provider` | string|null | 否 |
