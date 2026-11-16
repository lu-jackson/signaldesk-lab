# SignalDesk Lab 學習導讀（繁體中文）

這份導讀把專案拆成 10 個小單元，每個約 20–40 分鐘。每個單元固定五步：**先看結果 → 看哪個函式 → 一個小修改 → 怎麼驗證 → 一個理解問題**。不用一次讀完，也不要一次讀整個專案。

## 開始之前（只做一次）
1. 照 `GETTING_STARTED.md` 啟動，打開 http://127.0.0.1:8000。
2. **強烈建議**先在專案根目錄做一次快照，之後每個練習都能還原：
```bash
git init
git add -A
git commit -m "學習起點"
```
（`.gitignore` 已排除 venv、DB、金鑰。）每個「小修改」之後，用 `git checkout -- <檔案>` 還原，再 `python scripts/launcher.py test` 確認回到全綠。
3. 後端測試指令（在 `backend/` 內）：
```bash
.venv/Scripts/python -m pytest tests -q          # Windows
.venv/bin/python -m pytest tests -q              # macOS/Linux
```
下面「怎麼驗證」多半是挑一個測試跑：`pytest tests/檔案.py::測試名 -q`。

> 名詞慣例：每個新名詞第一次出現時會先用一句白話定義。

---

## 單元 1：從按下「搜尋」到資料庫，完整走一趟
**名詞**：*HTTP request*＝瀏覽器請後端做事的一個訊息；*FastAPI route*＝後端裡「某個網址對應哪個函式」；*SQLite*＝存成一個檔案的資料庫。

1. **先看結果**：到「專案與搜尋」，按「多益備考需求追蹤」的「立即執行並看結果」。看到下方結果表出現原文、納入／排除原因。
2. **看哪個函式**（照順序）：
   - 前端按鈕：`frontend/src/pages/Projects.tsx` 的 `runNow` → 呼叫 `frontend/src/api.ts` 的 `post()`。
   - 後端入口：`backend/app/routers/core.py` 的 `project_run_now`（`sync=true`）。
   - 實際工作：`backend/app/services/pipeline.py` 的 `execute_run` → `search_candidates` → `providers/social.py` 的 `DemoSocial.search_posts`（一句 SQL）。
   - 寫回資料庫：`record_candidates`（寫 `evaluations` 表）。
3. **一個小修改**：先備份（見上），把 `pipeline.py` `search_candidates(... limit: int = 200)` 的 `200` 改成 `5`，重新啟動，再按一次執行。
4. **怎麼驗證**：結果的「候選」數最多 5；跑 `pytest tests/test_flow.py -q`，看哪個測試失敗、失敗訊息指向哪一行。還原後再跑一次。
5. **理解問題**：為什麼 `execute_run` 要先建立 `runs` 那一列（`create_run`），而不是最後才一次寫入？（提示：看 `finish_run` 與失敗時的 `except`。）

## 單元 2：SQL 表、主鍵、外鍵，以及為什麼狀態要存資料庫
**名詞**：*主鍵*＝每列的唯一編號；*外鍵（FK）*＝「這欄必須指向另一張表真實存在的列」；*約束（CHECK/UNIQUE）*＝資料庫自己拒絕不合法的資料。

1. **先看結果**：在「草稿審核」核准一份草稿後，**重新整理頁面**——狀態還在。再停掉服務重新啟動，還在。狀態在資料庫，不在前端記憶體。
2. **看哪個函式／檔案**：`backend/app/migrations/001_init.sql`（讀 `drafts`、`approvals`、`delivery_dedup` 三張表）；`backend/app/db.py` 的 `connect`（為什麼每個連線都要 `PRAGMA foreign_keys=ON`）與 `tx`（`BEGIN IMMEDIATE` 短交易）。
3. **一個小修改**：不改程式。在 `backend/` 執行：
```bash
.venv/Scripts/python -c "import sqlite3; c=sqlite3.connect('../data/signaldesk.db'); c.execute('PRAGMA foreign_keys=ON'); c.execute(\"INSERT INTO social_accounts(id,platform,handle,display_name,created_at) VALUES('x','x','realuser','n','t')\")"
```
   （macOS/Linux 把 `.venv/Scripts/python` 換成 `.venv/bin/python`。）
4. **怎麼驗證**：你會看到 `IntegrityError: CHECK constraint failed`。對照 `001_init.sql` 裡 `substr(handle,1,5)='demo_'` 那一行；再讀測試 `tests/test_misc.py::test_fk_and_check_enforced_at_db_level`。
5. **理解問題**：如果核准狀態只存在前端，重新整理後會發生什麼？「核准綁 `content_hash`」為什麼要存在 `approvals` 表而不是 `drafts.status` 一個欄位？

## 單元 3：資料取得、相關性、購買意圖，是三件不同的事
**名詞**：*取得*＝把候選貼文找出來；*相關*＝跟主題有關；*意圖*＝作者是不是在「找服務」。

1. **先看結果**：專案結果表同一列有三組資訊——「搜尋結果（納入／排除＋原因）」「意圖」「分類理由與證據」。被排除的貼文不會有意圖（沒分類）。
2. **看哪個函式**：取得＝`pipeline.search_candidates`（關鍵字、必要／排除條件、時間窗 `[now-days, now)`）；判斷＝`providers/ai_demo.py` 的 `classify_text`。兩者之間隔著資料表 `evaluations`（`included` 與 `intent` 是不同欄位）。
3. **一個小修改**：在專案編輯表單把「排除條件」多加一個詞（例如「模考」），再執行一次。
4. **怎麼驗證**：新的執行結果中，含「模考」的貼文被標為「命中排除條件「模考」」且沒有分類；對照測試 `tests/test_flow.py::test_search_excludes_ads_and_classifies_separately`。
5. **理解問題**：一篇「多益題庫已經找到了，謝謝大家」會被搜尋納入嗎？會被判成有購買意圖嗎？為什麼把這兩件事分開比合併好？

## 單元 4：規則／模板 vs. 真正的 LLM 推論
**名詞**：*規則*＝人寫死的 if/關鍵詞；*LLM 推論*＝把文字送給語言模型，由它輸出判斷；*schema 驗證*＝檢查模型輸出格式是否符合約定。

1. **先看結果**：畫面最上方模式列寫著「規則／模板（非 LLM）」。到 PR 風險頁看某篇的「理由（規則）」。
2. **看哪個函式**：`ai_demo.py` 的 `classify_text`（規則順序：injection → 已解決 → 廣告 → 抱怨 → 求助 → 經驗分享）與 `draft_text`；對照 `ai_anthropic.py` 的 `AnthropicAI.classify` / `_json_call`（Pydantic 驗證＋最多一次修復）。兩者共用 `providers/base.py` 的 `Classification`。
3. **一個小修改**：到 `ai_demo.py` 的 `COMPLAINT` 清單加入 `"報警"`。
4. **怎麼驗證**：在 `backend/` 跑 `python -m eval.evaluate`，看混淆矩陣裡 `complaint` 一欄：原本漏掉的 `e34` 是否被抓到、其他有沒有被誤傷；再讀 `tests/test_agent.py::test_live_invalid_json_one_repair_then_fail` 理解 Live 的格式修復。
5. **理解問題**：你為這 1 筆資料加詞，分數就變高了——這能證明分類器「更準」嗎？（提示：想想 fixtures 與規則是誰寫的。）

## 單元 5：tool schema、tool_use、tool_result 與 agent loop
**名詞**：*tool schema*＝告訴模型「有哪些工具、參數長怎樣」；*tool_use*＝模型說「我要呼叫工具 X」；*tool_result*＝我們執行後回報的結果，要帶同一個 call id；*agent loop*＝反覆「模型→工具→模型」直到結束。

1. **先看結果**：「AI 助手」頁按範例句。trace 區看每一步：assistant 的 `tool_use ... id=...`、user 的 `tool_result → 同一個 id`。
2. **看哪個函式**：`backend/app/services/agent.py`——`TOOL_DEFS`／`TOOLS`（schema 由 Pydantic 自動產生）、`run_tool`（白名單＋驗參）、`send_message`（迴圈、上限、逐個 tool_use 回 tool_result）。Demo 的「大腦」是 `ai_demo.py::_plan`，Live 的是 `ai_anthropic.py::agent_turn`。
3. **一個小修改**：把 `agent.py` 的 `MAX_TOOL_CALLS = 12` 改成 `2`，再用範例句。
4. **怎麼驗證**：助手狀態變成 `limit_reached`，超額的呼叫被標 `rejected` 且**仍有** tool_result；跑 `pytest tests/test_agent.py -q` 看 `test_live_tool_budget_exhaustion` 哪個斷言失敗。
5. **理解問題**：模型回了兩個 tool_use，為什麼一定要在同一則 user 訊息裡回兩個 tool_result？少回一個會怎樣？

## 單元 6：草稿版本、人工核准，以及為什麼改稿要讓核准失效
**名詞**：*content hash*＝把內容壓成一串短碼，內容變了短碼就變；*冪等（idempotent）*＝同一個動作做很多次，結果跟做一次一樣。

1. **先看結果**：草稿頁：核准 → 改一個字存檔 → 「核准有效」變成「未核准／已失效」，送出鈕又灰了。
2. **看哪個函式**：`services/drafts.py` 的 `edit_draft`、`approve`、`simulate_send`、`on_brand_updated`；`pipeline.content_hash`；`delivery.deliver`。
3. **一個小修改**（分三步，逐步拿掉保護層，每步都先備份、做完還原）：
   - ① 在 `edit_draft` 把 `UPDATE approvals SET revoked_at...` 那行註解掉；
   - ② 再把同一個 `UPDATE drafts SET ...` 裡的 `status='draft'` 拿掉；
   - ③ 最後把 `_out()` 裡 `ap["content_hash"] == d["content_hash"]` 的比對拿掉。
4. **怎麼驗證**：每做完一步都跑 `pytest tests/test_flow.py::test_approval_required_and_edit_invalidates_and_single_metering -q`。
   - ① 之後測試**仍然通過**：狀態退回 `draft` 與 hash 比對還在擋。
   - ② 之後測試在 `edited["status"] == "draft"` 那行失敗（測試也在守這一層）；但用 UI 或 curl 試「核准→改字→送出」，仍會被 409 擋下，因為 hash 比對還在。
   - ③ 三層都拿掉後，「核准→改字→送出」會**成功送出舊核准的內容**——這就是要有「雙重保險」的原因。
   還原後再跑一次確認全綠。
5. **理解問題**：為什麼連「品牌設定改版」也要撤銷未送出草稿的核准？

## 單元 7：背景工作、lease、retry、idempotency 與 unknown
**名詞**：*job*＝排隊等 worker 做的工作；*lease*＝worker 對 job 的「租約」，逾期視為 worker 掛了；*backoff*＝重試間隔越來越長；*unknown*＝不知道外部到底有沒有成功。

1. **先看結果**：「留言與私訊模擬」注入事件；把私訊的失敗注入設為 `unknown` 再注入一個新事件；到「工作與事件」看該 job 停在 `unknown`，投遞紀錄有「確認已送出／未送出」。
2. **看哪個函式**：`services/jobs.py` 的 `claim`（原子領取）、`recover_expired`（lease 過期）、`run_one`（重試／backoff）；`services/delivery.py` 的 `deliver`（dedup、reserve、結果狀態機）；`worker.py` 的 `tick`。
3. **一個小修改**：把 `recover_expired` 中 `side_effect` 那個分支的 `status='unknown'` 改成 `status='queued'`（先備份）。
4. **怎麼驗證**：`pytest tests/test_delivery_jobs.py::test_worker_crash_lease_recovery -q` 失敗；讀失敗訊息，想想若真的這樣改，worker 當掉後同一則私訊可能被送兩次。還原。再看 `test_unknown_outcome_stops_and_reconciles`。
5. **理解問題**：`rate_limit` 應該重試、`permission_revoked` 不該重試、`unknown` 又不一樣——三者在程式的哪裡被分開？

## 單元 8：名單去重、來源歷史、分頁與匯出
**名詞**：*去重*＝同一個人只留一筆；*分頁*＝一次只拿一小段；*CSV formula injection*＝儲存格以 `=` 開頭時，試算表會把它當公式執行。

1. **先看結果**：事件進來的留言者在「名單」只有一筆；再手動用同 handle 加一個不同來源，同一筆多一個來源、歷史多一行。匯出 CSV 與 JSON。
2. **看哪個函式**：`services/leads.py` 的 `upsert_lead`（`UNIQUE(platform,handle)`＋`INSERT OR IGNORE` 來源）、`_iter_all`（走完所有頁）、`export_csv`、`csv_safe`。
3. **一個小修改**：把 `csv_safe` 裡的 `"@"` 從開頭字元清單拿掉（先備份）。
4. **怎麼驗證**：`pytest tests/test_leads_tracking.py -q -k csv` 失敗，指出 `@cmd` 沒有被中和。還原。另跑 `test_export_covers_all_pages_and_history`，注意它用 `chunk=10` 強迫匯出跨多頁。
5. **理解問題**：「只匯出畫面上已載入的那一頁」會是什麼 bug？`_iter_all` 為什麼用 `rowid > last` 而不是 `OFFSET`？

## 單元 9：指標分母、時間篩選，以及 click／unique／conversion 的差別
**名詞**：*分母*＝比例的底；*半開區間 [from,to)*＝含起點、不含終點；*estimated unique*＝用隨機 cookie 估的不重複訪客。

1. **先看結果**：「連結與分析」切換「近 1 天／14 天」：卡片與長條圖加總一致。選到沒資料的區間時顯示「沒有資料」，比率顯示「—」而不是 0。
2. **看哪個函式**：`services/tracking.py` 的 `summary`、`_range`、`_rate`、`record_click`；前端 `Analytics.tsx` 的 `end`（取下一個整分鐘）。
3. **一個小修改**：把 `summary` 內點擊查詢的 `clicked_at<?` 改成 `clicked_at<=?`（先備份）。
4. **怎麼驗證**：`pytest tests/test_leads_tracking.py::test_analytics_empty_not_faked_and_halfopen -q` 失敗：邊界上的點擊被多算一筆。還原。
5. **理解問題**：「點擊」「估計不重複訪客」「成交」差在哪？為什麼本專案刻意不顯示已讀與成交？

## 單元 10：合成資料評估、confusion matrix 與一般化限制
**名詞**：*precision*＝說「是」的裡面有多少真的是；*recall*＝真的是的裡面抓到多少；*confusion matrix*＝列出每個真實類別被判成哪些類別的表。

1. **先看結果**：`cd backend` 後 `python -m eval.evaluate`：看混淆矩陣與 2 個失誤。
2. **看哪個檔案**：`backend/eval/fixtures.json`（人工標註，與 runtime 規則分離）、`backend/eval/evaluate.py`（`_ratio` 對零分母回 `None`）、測試 `tests/test_misc.py::test_eval_report_zero_denominator_safe`。
3. **一個小修改**：在 `fixtures.json` 末尾新增一筆你自己寫的句子與標註。
4. **怎麼驗證**：重跑 `python -m eval.evaluate`，看 `n` 加一、矩陣哪格變動；若是新的失誤，它會列在 `MISS`。
5. **理解問題**：36 筆都是同一個作者寫的句子，這個 0.944 能代表「真實社群」嗎？要怎麼設計一個比較誠實的評估？（提示：不同來源、不同寫法、不讓規則作者看過。）

---

## 學完之後
- 想看全局：`CODE_MAP.md`（8–12 個值得先看的檔案與順序）。
- 遇到怪現象：`DEBUGGING_EXAMPLES.md`（三個可安全重現的錯誤）。
- 想向別人介紹：`CASE_STUDY_NOTES.md`（可展示／不可聲稱的內容與學習紀錄模板）。
