# SignalDesk Lab｜社群商機與互動代理實驗室

個人學習專案：本機可運行的「品牌設定 → 搜尋合成貼文 → 意圖／風險分類 → 草稿 → 人工審核 → 模擬送出 → 名單與分析」工作台，含背景工作、事件重播、使用量帳本與可呼叫工具的 AI 助手。
**所有資料為合成、所有投遞只寫入本機；Demo 模式是規則／模板，不是 LLM；不需要任何金鑰。**

**線上展示（唯讀沙盒，合成資料、投遞皆為模擬，可能因主機離線而暫時無法開啟）：https://signaldesk.moreti.app**

## 快速開始
```bash
python scripts/launcher.py setup     # 一次：venv、依賴（鎖版）、npm ci、build
python scripts/launcher.py start     # 啟動 API + 單一 worker
```
開啟 http://127.0.0.1:8000 。Windows 也可用 `scripts\setup.ps1`／`scripts\dev.ps1`。

## 文件
| 想做什麼 | 讀這個 |
|---|---|
| 安裝、啟動、環境變數 | [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) |
| 10 分鐘 Demo | [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md) |
| **開始學習（先讀這個）** | [docs/LEARNING_GUIDE_ZH-TW.md](docs/LEARNING_GUIDE_ZH-TW.md)、[CODE_MAP](docs/CODE_MAP.md)、[DEBUGGING_EXAMPLES](docs/DEBUGGING_EXAMPLES.md) |
| 架構／API／決策 | [ARCHITECTURE](docs/ARCHITECTURE.md)、[API](docs/API.md)、[DECISIONS](docs/DECISIONS.md) |
| 測試結果與限制 | [TEST_REPORT](docs/TEST_REPORT.md)、[KNOWN_LIMITATIONS](docs/KNOWN_LIMITATIONS.md) |
| 進度／案例筆記 | [PROGRESS](docs/PROGRESS.md)、[CASE_STUDY_NOTES](docs/CASE_STUDY_NOTES.md) |
| 原始規格（交接包） | `docs/DEVELOPMENT_SPEC.md`、`docs/ACCEPTANCE_AND_LEARNING.md`、`CLAUDE.md` |

## 測試
```bash
python scripts/launcher.py test   # 後端 pytest + 前端 typecheck/build
python scripts/launcher.py e2e    # Playwright 瀏覽器 E2E
```

## 邊界（務必讀）
Anthropic Live AI 與 Threads 唯讀 adapter 已實作並有 mock 測試，但**沒有對真實服務驗證**；僅 Windows 11 實測；單使用者、僅限 localhost，不可公開部署。詳見 KNOWN_LIMITATIONS。
