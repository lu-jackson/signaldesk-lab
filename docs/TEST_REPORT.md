# 測試報告（真實執行結果）

環境：Windows 11 Home 10.0.26300｜Python 3.14.5｜Node v24.19.0 / npm 11.17.0｜pytest 9.2.0｜Playwright 1.65.2（使用本機 Microsoft Edge，`channel="msedge"`，headless）｜執行日期 2026-11-16。
所有測試使用臨時 SQLite DB（pytest `tmp_path`／E2E 臨時目錄），**沒有碰** `data/signaldesk.db`；時鐘在單元測試中凍結在 `2026-11-16T12:00:00Z`。

## 實際執行的命令與結果

| # | 命令（工作目錄） | exit code | 結果 |
|---|---|---|---|
| 1 | `python -m pytest tests -q`（`backend/`，venv python） | 0 | **91 passed** in 11.88 s |
| 2 | `npm run typecheck`（`frontend/`，= `tsc --noEmit`，TypeScript 7.0.2） | 0 | 無錯誤 |
| 3 | `npm run build`（`frontend/`，tsc + vite 8.3.8） | 0 | built，29 modules，JS 275 kB（gzip 84 kB） |
| 4 | `python -m pytest e2e -q -p no:cacheprovider`（repo 根目錄） | 0 | **4 passed** in 13.71 s |
| 5 | `python -m eval.evaluate`（`backend/`） | 0 | 見下方分類評估 |
| 6 | `python scripts/launcher.py start` + `curl /api/health` | — | health `ok`、worker alive、`GET /` 200（之後已停止） |

開發過程中曾出現的失敗與修正（保留記錄，不隱藏）：
- E2E 初版：結果表分頁導致「被排除貼文」不在第一頁（測試改用 API 驗證排除筆數）；草稿卡片在 `reload()` 時因 `loading` 重新掛載而遺失「送出結果」訊息（真實 UI bug，改為重新整理時保留舊資料）；分析頁的 `to` 取整分鐘導致剛發生的點擊被半開區間排除（真實 bug，改為下一個整分鐘）；注入失敗與 worker 處理有競態（測試先等第一個事件完成）；Playwright 的 HeadlessChrome UA 正確地被判成 bot（測試改帶一般 UA）。
- 後端：一個測試（Live 未配置）原本預期建立會話即報錯，實際在送訊息時才丟 `NotConfigured`，已調整測試以符合設計；一個 seed 測試少用 `app` fixture。

## 驗收表對照（A01–A24）

| 編號 | 自動化證據 |
|---|---|
| A01 | `scripts/launcher.py check` 的版本檢查與錯誤訊息；實際 start 驗證（命令 6）。**僅 Windows 驗證。** |
| A02 | 全部測試在無金鑰環境（conftest 清掉 `ANTHROPIC_*`/`THREADS_*`）下執行；`test_demo_mode_labels_are_honest`、E2E 模式列斷言。 |
| A03 | `test_flow.py::test_brand_project_persist_across_restart`；E2E 流程一「reload 後仍存在」。 |
| A04 | `test_search_excludes_ads_and_classifies_separately`、`test_classifier_never_reads_answer_columns`。 |
| A05 | `test_approval_required_and_edit_invalidates_and_single_metering`、`test_idempotency_key_replays_response`；E2E 流程一。 |
| A06 | `test_duplicate_event_accepted_once`、`test_workflow_version_change_does_not_resend`、`test_process_existing_is_idempotent`；E2E 重複事件。 |
| A07 | `test_public_ok_dm_terminal_failure_independent`；E2E（DM `failed_terminal`、公開回覆 `simulated_sent`、已讀＝平台未回報）。 |
| A08 | `test_unknown_outcome_stops_and_reconciles`。 |
| A09 | `test_worker_crash_lease_recovery`、`test_claim_is_atomic_single_winner`、`test_worker_singleton_heartbeat`。 |
| A10 | `test_cancel_partial_keeps_results`。 |
| A11 | `test_same_handle_multi_sources_one_lead`；E2E 名單去重。 |
| A12 | `test_export_covers_all_pages_and_history`（chunk=10 強迫多頁、55 筆）、`test_csv_formula_injection_neutralised`、`test_csv_export_neutralises_malicious_note`。 |
| A13 | `test_dangerous_destinations_rejected`（7 種）、`test_click_redirect_only_to_stored_destination`、`test_click_vs_unique_vs_bot`；E2E。 |
| A14 | `test_analytics_empty_not_faked_and_halfopen`、`test_card_and_chart_consistent`；E2E 切換 1/14 天，卡片＝圖表加總。 |
| A15 | `test_demo_assistant_creates_real_drafts_zero_delivery`、`test_demo_reports_actual_count_when_short`；E2E 助手。 |
| A16 | `test_live_roundtrip_multiple_tools_keeps_call_ids`、`test_live_tool_error_is_reported_not_faked`（mock client，**未呼叫真實 API**）。 |
| A17 | `test_write_requires_proposal_and_ui_confirm`、`test_live_cannot_confirm_its_own_proposal`、`test_no_agent_tool_can_confirm_or_send`。 |
| A18 | `test_live_turn_limit_exhaustion_ends`、`test_live_tool_budget_exhaustion`。 |
| A19 | `test_malicious_post_gets_no_draft`、`test_malicious_post_does_not_leak_or_run_tools`、`test_live_disallowed_tool_and_bad_args_rejected`。 |
| A20 | `test_live_not_configured_no_fallback_no_request`、`test_threads_not_configured`、`test_threads_unconfigured_does_not_block_demo`、`test_live_api_error_surfaces`。 |
| A21 | `test_schedule_tick_enqueues_once_and_run_now_independent`（凍結時鐘、`clock.advance`）。 |
| A22 | `test_reserve_settle_release_idempotent`、`test_insufficient_units_rolls_back_whole_delivery`、`test_ledger_is_unique_per_operation_and_type`。 |
| A23 | 命令 1–4 的真實輸出。 |
| A24 | `e2e/test_e2e.py` 兩條流程＋助手＋error/retry 狀態。 |

另有：依賴錯誤碼（`test_status_codes`、`test_threads_error_codes` 401/403/429）、分頁、unique/FK/CHECK（`test_fk_and_check_enforced_at_db_level`）、timestamp 半開邊界、Origin 檢查、設定不外洩 secret。

## 合成資料分類評估（`eval/evaluate.py`，36 筆人工標註 vs Demo 規則）

- 意圖 accuracy **0.944（34/36）**；relevant precision 0.955、recall 0.955；risk 完全吻合 35/36。
- 混淆矩陣（列＝人工、欄＝規則；順序 seeking, advice, promotion, complaint, other）：

```
seeking    [11, 0, 0, 0, 0]
advice     [ 0, 3, 0, 0, 0]
promotion  [ 0, 0, 4, 0, 0]
complaint  [ 0, 0, 0, 7, 1]
other      [ 1, 0, 0, 0, 9]
```
- 兩個失誤：`e32`「想找人聊聊咖啡豆烘焙的差異」被「想找」關鍵字誤判為 seeking；`e34`「補習班說不退費，我要報警處理」沒有命中抱怨詞表就落入 other（詞表缺口）。**沒有為了提高分數而針對 fixtures 調整規則。**
- 零分母一律回 `None`（顯示 n/a），不當作 0 或 1（`test_eval_report_zero_denominator_safe`）。
- 品牌換成 moreti.app 的多益與電子筆記後，fixtures 是以原句型平行改寫，所以結果與之前相同；這也代表它**不是**對新領域的獨立驗證。
- 限制：36 筆是作者自己寫的合成句子，與規則同源於同一個人的語感，**這個分數不代表真實世界表現**，也不代表商業成效。

## 未驗證（如實列出）

- **Anthropic Live**：沒有 API key，從未對真實 API 發請求；只有 mock client 的 contract tests（tool_use、text、錯誤、無效 JSON＋一次修復、多工具、額度耗盡）。
- **Threads 唯讀 adapter**：沒有授權 token，從未對真實 Threads 發請求；endpoint／欄位依官方 keyword search 文件撰寫，只用 `httpx.MockTransport` 測 401/403/429、分頁與對應。
- **macOS / Linux**：`launcher.py`、`setup.sh`、`dev.sh` 已撰寫但**未在這兩個平台執行**。
- 瀏覽器：只用 Edge（Chromium）；未測 Firefox/Safari、平板與手機實機（CSS 有 media query，僅在 Windows 視窗縮放下看過）。
- 沒有負載／併發壓測；SQLite 原子 claim 只用單 process 內的測試與邏輯驗證（`BEGIN IMMEDIATE`）。
