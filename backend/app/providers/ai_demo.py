"""Demo AI：可讀的「規則／模板」，不是 LLM，也不輸出機率。

* classify：依序比對關鍵詞規則；每個結論都附 reason 與原文 evidence。
  它只看貼文文字，完全不讀任何標註欄位（資料庫也沒有這種欄位）。
* draft：把品牌「可確認事實」和 FAQ 套進模板，不捏造任何價格、優惠或保證。
* agent_turn：scripted planner（模擬規劃），依對話中已有的 tool_result 決定下一步，
  與真實 tool-use 共用同一個 agent loop 與工具執行器。
"""
from __future__ import annotations

import re

from .base import AgentTurn, Classification, ToolUse

INJECTION = [
    r"忽略.{0,8}(規則|指令|設定|提示)", r"無視.{0,8}(規則|指令)", r"ignore (all |any |the )?(previous|above|prior)",
    r"system prompt", r"api[ _-]?key", r"金鑰", r"洩漏", r"刪除所有", r"你現在是", r"jailbreak", r"reveal .{0,20}(key|secret|prompt)",
]
PROMOTION = ["【出租】", "【招生】", "【開幕", "歡迎洽詢", "加line", "加 line", "限時優惠", "免服務費", "佣金", "立即預約", "團購", "開幕優惠", "私訊報價", "歡迎預約", "優惠價"]
RESOLVED = ["已經找到", "已找到", "已解決", "已經解決", "搞定了", "已經訂到", "已訂到", "不用推薦了", "謝謝大家的建議"]
COMPLAINT = ["太誇張", "被坑", "亂扣", "退款", "詐騙", "爛透", "失望", "崩潰", "客訴", "黑店", "不會再", "糟透", "雷店", "踩雷", "又漲"]
SARCASM = ["呵呵", "真是太棒了", "真感謝", "謝謝喔", "好棒棒", "真是謝謝"]
LEGAL = ["律師", "提告", "消保", "消基會", "爆料", "媒體", "詐騙", "報警", "法院"]
SEEKING = ["想找", "求推薦", "有人推薦", "推薦嗎", "推薦哪", "請問", "有沒有", "有人知道", "想租", "想買", "想訂", "想學", "找不到", "需要幫忙", "求介紹", "哪裡有", "哪裡可以", "哪家"]
ADVICE = ["分享", "心得", "經驗", "提醒大家", "給新手", "注意事項", "懶人包"]
SENSITIVE = ["押金", "合約", "糾紛", "違約", "租約"]


def _snippet(text: str, needle: str, width: int = 22) -> str:
    i = text.lower().find(needle.lower())
    if i < 0:
        return text[:width * 2]
    return text[max(0, i - width): i + len(needle) + width]


def _first(text: str, words: list[str]) -> str | None:
    low = text.lower()
    for w in words:
        if w.lower() in low:
            return w
    return None


def classify_text(text: str) -> Classification:
    for pat in INJECTION:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return Classification(
                relevant=False, intent="other", risk="high", flags=["prompt_injection"],
                reason="貼文含要求改變系統行為或索取機密的指令文字；一律視為不可信資料，不執行也不回覆。",
                evidence=_snippet(text, m.group(0)))
    if w := _first(text, RESOLVED):
        return Classification(relevant=False, intent="other", risk="low",
                              reason=f"貼文表示需求已解決（出現「{w}」），不需要再回覆。", evidence=_snippet(text, w))
    if w := _first(text, PROMOTION):
        return Classification(relevant=False, intent="promotion", risk="low",
                              reason=f"貼文是商家／仲介宣傳（出現「{w}」），不是潛在客戶需求。", evidence=_snippet(text, w))
    neg = _first(text, COMPLAINT)
    sar = _first(text, SARCASM)
    if neg or (sar and _first(text, ["又漲", "亂", "扣", "沒人", "慘", "貴"])):
        trig = neg or sar
        legal = _first(text, LEGAL)
        risk = "high" if legal else "medium"
        why = f"貼文語氣為抱怨（出現「{trig}」）" + ("，並提到法律／媒體字眼「%s」，需 PR 人工處理。" % legal if legal else "，建議人工審核再決定是否回應。")
        if sar and not neg:
            why = f"貼文使用反諷語氣（「{sar}」搭配負面描述），判為抱怨；規則偵測反諷的能力有限。"
        return Classification(relevant=True, intent="complaint", risk=risk, reason=why, evidence=_snippet(text, trig),
                              flags=["sarcasm"] if sar and not neg else [])
    if w := _first(text, SEEKING):
        sens = _first(text, SENSITIVE)
        return Classification(relevant=True, intent="seeking", risk="medium" if sens else "low",
                              reason=f"貼文明確在找服務或推薦（出現「{w}」）。" + (f" 內容涉及「{sens}」，建議人工確認再回覆。" if sens else ""),
                              evidence=_snippet(text, w))
    if w := _first(text, ADVICE):
        return Classification(relevant=True, intent="advice", risk="low",
                              reason=f"貼文是經驗分享（出現「{w}」），不是求助，只觀察不回覆。", evidence=_snippet(text, w))
    return Classification(relevant=False, intent="other", risk="low",
                          reason="雖含搜尋關鍵字，但沒有明確需求或意圖訊號。", evidence=text[:40])


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def draft_text(post: dict, brand: dict, evaluation: dict) -> str:
    data = brand["data"]
    ptxt = _bigrams(post["text"])
    facts = sorted(data.get("facts", []), key=lambda f: -len(_bigrams(f) & ptxt))[:2]
    faq_best = None
    best = 0
    for item in data.get("faq", []):
        sc = len(_bigrams(item.get("q", "")) & ptxt)
        if sc > best:
            best, faq_best = sc, item
    parts = [f"Hi {post['author_handle']}，看到你的貼文，我是{brand['name']}的小編。"]
    if faq_best and best >= 2:
        parts.append(faq_best["a"])
    parts += [f"{f}" for f in facts]
    if data.get("cta"):
        parts.append(data["cta"])
    body = "\n".join(parts)
    for bad in data.get("forbidden", []):
        if bad and bad in body:
            body = body.replace(bad, "")
    return body.strip()


class DemoAI:
    name = "demo"
    label = "規則／模板（非 LLM）"

    def classify(self, post_text: str, project: dict) -> Classification:
        return classify_text(post_text)

    def draft(self, post: dict, brand: dict, evaluation: dict) -> str:
        return draft_text(post, brand, evaluation)

    # ---- scripted planner（模擬規劃）----
    def agent_turn(self, messages: list[dict], tools: list[dict], system: str) -> AgentTurn:
        # 只看「最近一則使用者文字」之後的對話，避免同一會話第二個請求沿用上一輪的結果
        start = 0
        for i, m in enumerate(messages):
            c = m["content"]
            if m["role"] == "user" and (isinstance(c, str) or any(b.get("type") == "text" for b in c)):
                start = i
        return _plan(messages[start:])


_CN = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _num(tok: str) -> int | None:
    if tok.isdigit():
        return int(tok)
    return _CN.get(tok)


def _blocks(messages: list[dict]):
    for m in messages:
        c = m["content"]
        if isinstance(c, str):
            yield m["role"], {"type": "text", "text": c}
        else:
            for b in c:
                yield m["role"], b


def _results(messages: list[dict]) -> dict[str, dict]:
    """tool name → 最近一次 tool_result 的 JSON。"""
    import json
    names: dict[str, str] = {}
    out: dict[str, dict] = {}
    for _, b in _blocks(messages):
        if b.get("type") == "tool_use":
            names[b["id"]] = b["name"]
        elif b.get("type") == "tool_result":
            try:
                out.setdefault(names.get(b["tool_use_id"], "?"), []).append(
                    {"error": b.get("is_error", False), "data": json.loads(b["content"]) if isinstance(b["content"], str) else b["content"]})
            except Exception:
                out.setdefault(names.get(b["tool_use_id"], "?"), []).append({"error": True, "data": {}})
    return out


def _plan(messages: list[dict]) -> AgentTurn:
    goal = ""
    for role, b in _blocks(messages):
        if role == "user" and b.get("type") == "text":
            goal = b["text"]
            break
    res = _results(messages)
    errs = [n for n, v in res.items() if any(x["error"] for x in v)]
    n_tool_results = sum(len(v) for v in res.values())
    tag = "【模擬規劃（scripted，非 LLM）】"

    def call(name: str, **inp) -> ToolUse:
        return ToolUse(id=f"demo_{name}_{n_tool_results}_{len(inp)}", name=name, input=inp)

    def turn(text: str, *uses: ToolUse) -> AgentTurn:
        blocks = ([{"type": "text", "text": text}] if text else []) + [
            {"type": "tool_use", "id": u.id, "name": u.name, "input": u.input} for u in uses]
        return AgentTurn(text=text, tool_uses=list(uses), stop_reason="tool_use" if uses else "end_turn", raw_blocks=blocks)

    if errs:
        return turn(f"{tag}工具回報錯誤：{', '.join(errs)}。我不會假裝成功，請調整後重試。")

    handle_m = re.search(r"(demo_[a-z0-9_]+)", goal)
    if re.search(r"(名單|lead)", goal, re.I) and not (handle_m and re.search(r"(標記|設為|改成|Qualified|Ignored)", goal, re.I)):
        if "list_leads" not in res:
            return turn(f"{tag}查看名單。", call("list_leads"))
        d = res["list_leads"][-1]["data"]
        return turn(f"{tag}目前名單共 {d.get('total', 0)} 筆（顯示前 {len(d.get('items', []))} 筆）。")
    if handle_m and re.search(r"(標記|設為|改成|Qualified|Ignored|Converted)", goal, re.I):
        status = "Qualified"
        for s in ("Ignored", "Converted", "Qualified", "New"):
            if s.lower() in goal.lower():
                status = s
        if "propose_lead_update" not in res:
            return turn(f"{tag}修改名單屬於寫入動作，我只能建立提案，需要你在 UI 確認。",
                        call("propose_lead_update", platform="threads", handle=handle_m.group(1), status=status, reason="助手依使用者要求建立"))
        return turn(f"{tag}已建立名單更新提案，尚未生效；請到「助手」頁的提案區按確認。")
    if re.search(r"(狀態|執行結果|run status)", goal, re.I) and "搜尋" not in goal:
        if "get_run_status" not in res:
            return turn(f"{tag}查詢最近一次執行。", call("get_run_status"))
        d = res["get_run_status"][-1]["data"]
        return turn(f"{tag}最近執行：{d.get('status', '無紀錄')}，候選 {d.get('candidates', 0)}、已分類 {d.get('classified', 0)}、草稿 {d.get('drafts', 0)}。")

    if not re.search(r"(搜尋|找|查)", goal):
        return turn(f"{tag}我只支援固定範圍的句型：搜尋近 N 天某主題貼文並替前 N 篇備草稿、查看名單、標記名單、查執行狀態。這是 scripted 規劃，不是 LLM。")

    # ---- 搜尋 + 草稿 流程 ----
    if "list_projects" not in res:
        return turn(f"{tag}先看有哪些專案。", call("list_projects"))
    projects = res["list_projects"][-1]["data"].get("items", [])
    chosen = next((p for p in projects if any(k in goal for k in p["keywords"]) or p["name"] in goal), None)
    if not chosen:
        return turn(f"{tag}找不到與「{goal[:30]}」相符關鍵字的專案，所以沒有搜尋。請先建立專案。")
    m = re.search(r"(\d+|[一二兩三四五六七八九十])\s*天", goal)
    days = _num(m.group(1)) if m else (7 if "一週" in goal or "一周" in goal else chosen.get("window_days", 7))
    mt = re.search(r"前\s*(\d+|[一二兩三四五六七八九十])\s*篇", goal)
    want = _num(mt.group(1)) if mt else 3
    extra = ["仲介"] if "仲介" in goal else []
    if "get_brand" not in res:
        return turn(f"{tag}讀取品牌設定。", call("get_brand", brand_id=chosen["brand_id"]))
    if "search_demo_posts" not in res:
        return turn(f"{tag}搜尋近 {days} 天、排除 {extra or '專案預設條件'} 的貼文。",
                    call("search_demo_posts", project_id=chosen["id"], days=days, extra_exclude=extra, limit=50))
    sr = res["search_demo_posts"][-1]["data"]
    ids = [p["post_id"] for p in sr.get("items", [])]
    if not ids:
        return turn(f"{tag}搜尋結果為 0 筆，未建立任何草稿，也沒有送出。")
    if "classify_posts" not in res:
        return turn(f"{tag}對 {len(ids)} 篇候選做分類。", call("classify_posts", run_id=sr["run_id"], post_ids=ids))
    cls = res["classify_posts"][-1]["data"].get("items", [])
    pick = [c["post_id"] for c in cls if c.get("intent") == "seeking" and c.get("risk") != "high" and c.get("relevant")][:want]
    if pick and "prepare_draft" not in res:
        return turn(f"{tag}替前 {len(pick)} 篇有明確需求的貼文準備草稿（不會送出）。",
                    *[ToolUse(id=f"demo_prepare_draft_{i}", name="prepare_draft", input={"project_id": chosen["id"], "post_id": pid})
                      for i, pid in enumerate(pick)])
    made = [x for x in res.get("prepare_draft", [])]
    ok = sum(1 for x in made if x["data"].get("draft_id"))
    shortage = f"（你要求 {want} 篇，實際只有 {len(pick)} 篇符合）" if len(pick) < want else ""
    return turn(f"{tag}完成：候選 {len(ids)} 篇，其中明確求助且非高風險 {len(pick)} 篇，已建立草稿 {ok} 份{shortage}。"
                f"零份送出，請到「草稿」頁審核。")
