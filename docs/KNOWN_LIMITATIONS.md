# 已知限制

## 沒有驗證過的（外部邊界）
- **Anthropic Live**：沒有 API key，從未發出真實請求。`providers/ai_anthropic.py` 只用假 client 做 contract tests。SDK 實際回傳格式、模型對工具 schema 的行為、token 計量都**未實測**。
- **Threads 唯讀**：沒有授權帳號／權限。endpoint 與欄位依官方 keyword search 文件撰寫，只用 `httpx.MockTransport` 測。UI 會顯示「未配置／未實測」。`list_comments` 刻意未實作。
- **macOS / Linux**：啟動器與 sh 腳本未在這兩個平台跑過。
- 只在 Edge（Chromium）跑過瀏覽器測試；沒有實機手機／平板測試。

## Demo 的本質限制
- **Demo AI 是規則，不是 LLM**：中文關鍵詞比對，不懂上下文。反諷、否定、委婉表達、新詞都會漏判（評估見 TEST_REPORT：36 筆合成句、意圖 accuracy 0.944，且 fixtures 與規則同一作者，分數不能推論到真實資料）。規則輸出沒有機率，`risk` 只是建議等級。
- **Demo 搜尋是關鍵字＋時間 SQL**，不是向量／語意搜尋。只涵蓋 120 篇合成貼文。
- **Demo 草稿是模板**：只組合品牌「可確認事實」、FAQ 與 CTA，品質平淡；有「不可承諾事項」過濾，但這只是字串檢查。
- **Demo 助手是 scripted planner**：只支援幾個固定句型（搜尋＋草稿、查名單、標記名單、查狀態）。
- 點擊與工程指標：`estimated_unique` 只靠隨機 cookie（清 cookie 或換瀏覽器就是新訪客）；bot 判斷只是 User-Agent 關鍵字；seed 內的 40 筆點擊與其國家／裝置是**合成**並標示；沒有已讀、成交資料。
- 用量帳本是虛擬 units，費率是示例，與任何真實 token／帳單無關。

## 設計上的範圍限制
- **單使用者、僅限 localhost**：沒有登入。Origin 檢查只能擋瀏覽器跨站寫入，**不是**可公開部署的安全模型。不要綁到 0.0.0.0 或公開網址。
- 投遞永遠是本機模擬；沒有真實發送開關。沒有 webhook 簽章 handler（只有無簽章的 simulator，僅本機）。
- Agent 的 `run`（send_message）在 HTTP request 內同步執行，最長受 timeout 限制（預設 90 秒）；沒有串流。
- 同一專案同一貼文只保留一份有效草稿（partial unique index）。
- SQLite：單機、單寫入者模型；`BEGIN IMMEDIATE` 保證 claim 原子，但沒有做多 process 壓力測試。
- 排程精度取決於 worker 輪詢（1 秒）與 `schedule_tick` 執行頻率。
- CSV 匯出以「單引號前綴」處理公式字首，Excel 開啟時會看到該前綴字元（這是刻意的安全取捨）。
- 前端沒有單元測試，僅 typecheck＋E2E；UI 沒有做完整的無障礙審查。
- 資料庫 schema 只有一個 migration（`001_init`）；沒有降版（down）migration。
