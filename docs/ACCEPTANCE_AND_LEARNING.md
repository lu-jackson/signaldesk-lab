# 驗收與學習交付要求

這份文件供 Claude Code 驗收，不要求使用者在開發期間逐步操作。

## 1. 核心驗收表

| 編號 | 情境 | 可判定結果 |
|---|---|---|
| A01 | 乾淨環境安裝與啟動 | 前置版本錯誤清楚；正確環境可 seed、啟動並開啟 UI。 |
| A02 | 無任何外部金鑰 | Demo 完整運行；沒有外部網路請求或假的 live 標籤。 |
| A03 | 建立品牌及追蹤專案 | 儲存 DB，重新整理及重啟後仍存在。 |
| A04 | 搜尋近期租屋需求並排除廣告 | 呈現來源原文、獨立分類及理由；規則不偷讀答案欄。 |
| A05 | 生成、修改、核准及模擬送出 | 無核准不可送；修改後舊核准失效；一次送出一次計量。 |
| A06 | 重複事件／重複點送出 | 相同副作用只產生一次；更改 workflow version 不重送同一 comment/channel。 |
| A07 | 公開回覆成功、DM 終局失敗 | 各自狀態明確，終局失敗不盲目 retry，沒有假已讀。 |
| A08 | 投遞結果未知 | 停在 unknown，需 reconcile，不當一般 retryable。 |
| A09 | worker 中途停止並重啟 | lease 可恢復安全工作；已做副作用不重複。 |
| A10 | 取消部分完成工作 | 保留既有結果，不再建立新副作用。 |
| A11 | 同平台同 handle 多來源 | 一個 lead、保留多來源及歷史。 |
| A12 | 多頁名單匯出 | 包含所有符合資料，JSON 含歷史；CSV 對公式字首安全處理。 |
| A13 | 追蹤連結 | 指向預設定的目的地；點擊與去重訪客有區別；拒絕危險 URL。 |
| A14 | 改時間範圍 | 卡片及圖表一致，空值不偽裝零。 |
| A15 | Demo assistant 的搜尋及草稿請求 | 寫入實際草稿、可看 trace，零送出；UI 標示 scripted。 |
| A16 | Anthropic mocked tool-use 往返 | 維持 call id，回正確 tool_result，能處理多工具及錯誤。 |
| A17 | agent 要求寫入 | 必須 proposal＋UI 確認；模型不能偽造確認，API 亦不可繞過。 |
| A18 | agent 回合／工具額度耗盡 | 結束並回可理解狀態，沒有無限 loop。 |
| A19 | 惡意原文要求忽略規則／洩漏 key | 不洩密、不執行任意工具；domain policy 仍生效。 |
| A20 | Live 未配置／授權錯誤 | 不呼叫未授權能力，不自動降成 Demo 冒充成功。 |
| A21 | 排程與 Run Now | 狀態清楚、去重、UTC 測試可控，不需等真實時間測。 |
| A22 | 使用量 reserve／settle／release | 重試不多扣，失敗按定義釋放，不出現無解釋負餘額。 |
| A23 | 前端 build/typecheck＋API tests | 真的執行並保存命令／結果，不把未跑說成通過。 |
| A24 | 瀏覽器端到端 | 覆蓋品牌到模擬投遞及事件到名單／分析兩條流程。 |

依賴錯誤、分頁、unique constraint、無效 enum、外鍵、timestamp 邊界亦需覆蓋。測試採臨時 DB，不能破壞使用者 Demo DB。不為每個 accessor 寫鏡像測試，優先測狀態與副作用。

## 2. 完成後一定要產出

| 檔案 | 必要內容 |
|---|---|
| `docs/GETTING_STARTED.md` | 實際測過的 Windows／macOS／Linux 安裝、啟動、停止、重啟、seed、reset 及環境變數。 |
| `docs/ARCHITECTURE.md` | 最終目錄、模組責任、資料模型、兩條資料流、agent loop、worker、已做／未做。 |
| `docs/API.md` | 與 FastAPI OpenAPI 一致的端點、狀態碼、schema 及範例。 |
| `docs/DEMO_WALKTHROUGH.md` | 10 分鐘操作腳本，逐步說要點哪裡和預期看到什麼。 |
| `docs/LEARNING_GUIDE_ZH-TW.md` | 見下一節；引用真實程式路徑、函式及測試。 |
| `docs/DECISIONS.md` | 重大設計、理由、限制；不填未採用的架構。 |
| `docs/TEST_REPORT.md` | 真實命令、exit code、數量、環境、E2E、未驗證外部服務；失敗保留說明。 |
| `docs/PROGRESS.md` | M0–M5 勾選、阻塞與下一步；可供中斷後接續。 |
| `docs/KNOWN_LIMITATIONS.md` | Demo、live、唯讀／模擬、單使用者與資料涵蓋限制。 |
| `.env.example` | 無秘密的可用範例；AI／社群／投遞開關獨立。 |

另提供 lockfile、migration、seed、測試、.gitignore；忽略 venv、node_modules、.env、DB、日誌及瀏覽器測試輸出。不要打包金鑰。

## 3. 學習導讀：每次只學一小段

文件用繁體中文，新概念先一句白話定義。使用者不需要一次讀完程式。以下 10 個單元，每單元控制成約 20–40 分鐘的活動，提供「先看結果 → 看哪個函式 → 一個小修改 → 怎麼驗證 → 一個理解問題」。

1. 從瀏覽器按搜尋，到 FastAPI 再到 SQLite 的完整一趟。
2. SQL 表、主鍵、外鍵與為什麼狀態要存 DB。
3. 資料取得、相關性、購買意圖的差別。
4. 規則／模板與真正 LLM 推論的差別。
5. tool schema、tool_use、tool_result 與 agent loop。
6. 草稿版本、人工核准與為什麼改稿要失效。
7. 背景工作、lease、retry、idempotency 與 unknown。
8. 名單去重、來源歷史、分頁與匯出。
9. 指標分母、時間篩選、click／unique／conversion 差別。
10. 合成資料評估、confusion matrix 與一般化限制。

不要用純名詞堆疊。每單元直接指向完成專案裡的真實檔案與函式，不可用不存在的路徑。練習只改一個規則／欄位／測試，提供還原方式；不要替學習者先做完練習。

附三個文件：
- `docs/CODE_MAP.md`：最值得先看的 8–12 個檔案，責任與閱讀順序。
- `docs/DEBUGGING_EXAMPLES.md`：三種可安全重現的錯誤，含症狀、trace、修復方法。
- `docs/CASE_STUDY_NOTES.md`：本專案可展示／不可聲稱的內容；架構取捨、測試結果、個人學習紀錄模板，不虛構實際用戶或商業成效。

## 4. 完成回覆格式

最多 10 行：完成項目、精確啟動命令、本機 URL、Demo 入口、測試摘要、Live 未實測項目、最先讀的學習文件。詳細內容放文件，不在聊天貼整個專案。

若系統權限／網路／工具限制真的阻擋，保存已完成工作、錯誤與最短恢復步驟；不可要求停用全部權限保護，也不可保證一個 prompt 能無限跨工作階段持續運行。
