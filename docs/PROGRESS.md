# 開發進度（可供中斷後接續）

最後更新：2026-11-16。狀態：**M0–M5 全部完成**，核心驗收 A01–A24 皆有對應的自動化測試（見 `TEST_REPORT.md`）。

| 里程碑 | 狀態 | 內容與驗證 |
|---|---|---|
| M0 環境／schema／seed／scripts | ✅ | Python 3.14.5、Node 24.19.0；`backend/app/migrations/001_init.sql`（29 張表＋schema_migrations（含 FK、UNIQUE、CHECK 約束））、`app/seed.py`、`scripts/launcher.py` + ps1/sh 包裝。驗證：migration 冪等測試、seed 計數／可重現測試、launcher 實際啟動並由 `/api/health` 確認。 |
| M1 品牌→搜尋→分類→草稿→核准→模擬送出 | ✅ | `services/pipeline.py`、`drafts.py`、`providers/ai_demo.py`；`tests/test_flow.py`（10）＋ E2E 流程一。 |
| M2 事件、工作、去重、失敗注入、名單與匯出 | ✅ | `services/jobs.py`、`delivery.py`、`automations.py`、`leads.py`、`worker.py`；`tests/test_delivery_jobs.py`（15）、`tests/test_leads_tracking.py`。 |
| M3 追蹤連結、分析、PR、排程、用量帳本 | ✅ | `services/tracking.py`、`ledger.py`、`worker.schedule_tick`；PR 頁＝`/api/evaluations?risk=`。 |
| M4 助手、Anthropic adapter、Threads 唯讀 | ✅ | `services/agent.py`、`providers/ai_anthropic.py`、`providers/social.py`；`tests/test_agent.py`（mocked tool-use）、`tests/test_misc.py`（Threads MockTransport）。**Live 皆未對真實服務驗證。** |
| M5 回歸、E2E、文件、學習導讀 | ✅ | pytest 89 passed；前端 typecheck/build exit 0；Playwright E2E 4 passed；本資料夾所有文件。 |

## 已驗證
- 後端 89 個 pytest、前端 `tsc --noEmit` 與 `vite build`、4 個 Playwright 瀏覽器測試（Edge channel）。
- 真的以 `python scripts/launcher.py start` 啟動，確認 `/api/health`（worker alive）、首頁 200、儀表板 API。

## 尚未驗證／阻塞
- 無阻塞。未驗證：Anthropic Live（沒有 key）、Threads 真實 API（沒有授權）、macOS/Linux 啟動（只在 Windows 11 測過）。詳見 `KNOWN_LIMITATIONS.md`。

## 下一步（若要繼續）
1. 想學習：從 `docs/LEARNING_GUIDE_ZH-TW.md` 單元 1 開始。
2. 想接 Live AI：把 key/model 填進 `.env`，在「設定」切換 AI_PROVIDER，先用 1–2 篇合成貼文試。
3. 重新驗收：`python scripts/launcher.py test` 與 `python scripts/launcher.py e2e`。
