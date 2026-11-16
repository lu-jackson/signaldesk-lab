#!/usr/bin/env python3
"""由 FastAPI OpenAPI 產生 docs/API.md（避免文件與實作不一致）。

用法：backend/.venv 的 python scripts/gen_api_doc.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["SIGNALDESK_DB"] = str(Path(tempfile.mkdtemp()) / "doc.db")

from app.main import create_app  # noqa: E402

HEAD = """# API 文件

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
curl -X POST http://127.0.0.1:8000/api/simulator/events -H "Content-Type: application/json" \\
  -d '{"event_id":"e1","post_id":"own_rent_1","author_handle":"demo_tester","text":"請給我清單"}'
```

## 端點

"""


def schema_name(s: dict | None) -> str:
    if not s:
        return "—"
    if "$ref" in s:
        return s["$ref"].split("/")[-1]
    if s.get("type") == "array":
        return f"array<{schema_name(s.get('items'))}>"
    return s.get("type", "object")


def main() -> None:
    spec = create_app(do_seed=False).openapi()
    out = [HEAD]
    groups: dict[str, list[str]] = {}
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            tag = path.split("/")[2] if path.startswith("/api/") and len(path.split("/")) > 2 else "other"
            body = (op.get("requestBody", {}).get("content", {}).get("application/json", {}) or {}).get("schema")
            params = [f"`{p['name']}`{'*' if p.get('required') else ''}" for p in op.get("parameters", []) if p["in"] in ("query", "header")]
            codes = ", ".join(sorted(op["responses"].keys()))
            groups.setdefault(tag, []).append(
                f"| `{method.upper()}` | `{path}` | {schema_name(body) if body else '—'} | {', '.join(params) or '—'} | {codes} | {op.get('summary', '')} |")
    for tag in sorted(groups):
        out.append(f"### {tag}\n\n| 方法 | 路徑 | Body schema | 參數（* 必填） | 回應碼 | 函式 |\n|---|---|---|---|---|---|\n" + "\n".join(groups[tag]) + "\n")
    out.append("## Schemas\n")
    for name, sc in sorted(spec["components"]["schemas"].items()):
        if name in ("HTTPValidationError", "ValidationError"):
            continue
        props = sc.get("properties", {})
        req = set(sc.get("required", []))
        out.append(f"### {name}\n\n| 欄位 | 型別 | 必填 |\n|---|---|---|")
        for k, v in props.items():
            t = v.get("type") or ("enum" if "enum" in v else schema_name(v) if "$ref" in v else "|".join(a.get("type", "?") for a in v.get("anyOf", [])) or "any")
            if "enum" in v:
                t = "enum(" + "/".join(map(str, v["enum"])) + ")"
            out.append(f"| `{k}` | {t} | {'是' if k in req else '否'} |")
        out.append("")
    (ROOT / "docs" / "API.md").write_text("\n".join(out), encoding="utf-8")
    print("docs/API.md 已產生，端點數：", sum(len(v) for v in spec["paths"].values()))


if __name__ == "__main__":
    main()
