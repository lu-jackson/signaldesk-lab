"""A24：兩條關鍵瀏覽器流程 + 助手。
流程一：品牌 → 專案 → 搜尋/分類 → 草稿 → 核准 → 修改使核准失效 → 再核准 → 模擬送出。
流程二：事件 → worker 投遞 → 名單 → 追蹤連結點擊 → 分析卡片/圖表一致。
"""
from __future__ import annotations

import re
import uuid

from playwright.sync_api import expect


def goto(page, route):
    page.goto(f"{page.base}/#/{route}")
    page.wait_for_load_state("networkidle")


def test_flow1_brand_to_simulated_send(page):
    goto(page, "dashboard")
    expect(page.get_by_test_id("modebar")).to_contain_text("規則／模板（非 LLM）")
    expect(page.get_by_test_id("modebar")).to_contain_text("僅本機模擬")

    # 1. 建立品牌
    goto(page, "brands")
    name = f"E2E 租屋品牌 {uuid.uuid4().hex[:4]}"
    page.get_by_test_id("brand-name").last.fill(name)
    page.get_by_test_id("brand-facts").last.fill("E2E 可確認事實：我們提供看房陪同。")
    page.get_by_test_id("brand-cta").last.fill("歡迎私訊。")
    page.get_by_test_id("brand-save").last.click()
    expect(page.get_by_text(name).first).to_be_visible()

    # 2. 建立專案（品牌／帳號用下拉選）
    goto(page, "projects")
    page.get_by_test_id("proj-name").last.fill("E2E 專案")
    page.get_by_test_id("proj-brand").last.select_option(label=name)
    page.get_by_test_id("proj-keywords").last.fill("租屋")
    page.get_by_test_id("proj-exclude").last.fill("仲介, 【出租】, 歡迎洽詢")
    page.get_by_test_id("proj-save").last.click()
    card = page.locator("section.card", has_text="E2E 專案").first
    expect(card).to_be_visible()

    # 3. 重新整理後仍存在（持久化）
    page.reload(); page.wait_for_load_state("networkidle")
    card = page.locator("section.card", has_text="E2E 專案").first
    expect(card).to_be_visible()

    # 4. 執行：搜尋 → 分類 → 草稿
    card.get_by_test_id(re.compile("run-sync-")).click()
    expect(page.get_by_test_id("run-msg")).to_contain_text("完成")
    rows = page.get_by_test_id("result-row")
    expect(rows.first).to_be_visible()
    run_id = re.search(r"run_[0-9a-f]+", page.locator("section.card", has_text="執行結果").first.inner_text()).group(0)
    ex = page.request.get(f"{page.base}/api/runs/{run_id}/results?included=false&page_size=100").json()
    assert ex["total"] >= 1 and all("排除" in e["inclusion_reason"] for e in ex["items"]), "應有被排除的廣告"
    expect(page.get_by_test_id("results")).to_contain_text("seeking")

    # 5. 草稿：未核准不能送；核准 → 修改使核准失效 → 再核准 → 送出
    goto(page, "drafts")
    first = page.locator("section.card").filter(has_text="E2E 可確認事實").first
    expect(first).to_be_visible()
    did = first.get_by_test_id(re.compile("draft-approve-")).get_attribute("data-testid").replace("draft-approve-", "")
    card = lambda: page.locator("section.card").filter(has=page.get_by_test_id(f"draft-approve-{did}"))
    send = page.get_by_test_id(f"draft-send-{did}")
    expect(send).to_be_disabled()
    page.get_by_test_id(f"draft-approve-{did}").click()
    expect(card()).to_contain_text("核准有效")
    expect(send).to_be_enabled()
    page.get_by_test_id(f"draft-body-{did}").fill("人工修改過的內容。")
    page.get_by_test_id(f"draft-save-{did}").click()
    expect(card()).to_contain_text("未核准／已失效")
    expect(send).to_be_disabled()
    page.get_by_test_id(f"draft-approve-{did}").click()
    expect(card()).to_contain_text("核准有效")
    send.click()
    expect(page.get_by_test_id(f"draft-out-{did}")).to_contain_text("simulated_sent")
    expect(page.get_by_test_id(f"draft-delivery-{did}")).to_contain_text("僅本機模擬")

    # 6. 儀表板有反映
    goto(page, "dashboard")
    expect(page.get_by_test_id("metric-simulated_deliveries")).to_contain_text("分母")


def test_flow2_event_to_leads_and_analytics(page):
    goto(page, "automations")
    eid = f"e2e-{uuid.uuid4().hex[:6]}"
    page.get_by_test_id("evt-id").fill(eid)
    page.get_by_test_id("evt-send").click()
    expect(page.get_by_test_id("evt-result")).to_contain_text("duplicate=false")
    page.get_by_test_id("evt-send").click()                   # 重複事件
    expect(page.get_by_test_id("evt-result")).to_contain_text("duplicate=true")

    # 先等第一個事件的兩個投遞都完成（避免與下面的失敗注入競爭）
    deliveries = page.get_by_test_id("deliveries")
    for _ in range(30):
        page.get_by_role("button", name="重新整理").first.click()
        page.wait_for_timeout(700)
        if deliveries.locator("tr[data-status='simulated_sent']").count() >= 2:
            break
    assert deliveries.locator("tr[data-status='simulated_sent']").count() >= 2
    # 注入 DM 終局失敗 → 第二個事件：公開回覆成功、DM failed_terminal
    page.get_by_test_id("inject-dm").select_option("permission_revoked")
    eid2 = f"e2e-{uuid.uuid4().hex[:6]}"
    page.get_by_test_id("evt-id").fill(eid2)
    page.get_by_test_id("evt-send").click()
    deliveries = page.get_by_test_id("deliveries")
    for _ in range(30):                                       # 等 worker（輪詢 1 秒）
        page.get_by_role("button", name="重新整理").first.click()
        page.wait_for_timeout(700)
        if deliveries.locator("tr[data-status='failed_terminal']").count() >= 1 and deliveries.locator("tr[data-status='simulated_sent']").count() >= 3:
            break
    expect(deliveries.locator("tr[data-status='failed_terminal']").first).to_contain_text("dm")
    assert deliveries.locator("tr[data-status='simulated_sent']").count() >= 3
    expect(deliveries).to_contain_text("平台未回報")            # 沒有假已讀
    page.get_by_test_id("inject-dm").select_option("none")

    # 名單：事件留言者進名單且去重
    goto(page, "leads")
    expect(page.get_by_test_id("leads")).to_contain_text("demo_tester")
    assert page.get_by_test_id("leads").get_by_text("demo_tester", exact=True).count() == 1
    page.get_by_text("詳情").first.click()
    expect(page.get_by_test_id("lead-detail")).to_contain_text("來源")
    page.get_by_test_id("lead-status").select_option("Converted")
    expect(page.get_by_test_id("lead-detail")).to_contain_text("不代表訂單")

    # 追蹤連結：建立 → 點擊 → 分析
    goto(page, "analytics")
    page.get_by_test_id("link-label").fill("E2E 連結")
    page.get_by_test_id("link-create").click()
    short = page.locator("table a").first.get_attribute("href")
    before = int(page.get_by_test_id("card-clicks").inner_text())
    r = page.request.get(short, max_redirects=0, headers={"user-agent": "Mozilla/5.0 (X11; Linux) Gecko/20100101 Firefox/120.0"})
    assert r.status == 302 and r.headers["location"].endswith("/demo-landing")
    page.get_by_role("button", name="重新整理").first.click()
    page.wait_for_timeout(500)
    expect(page.get_by_test_id("card-clicks")).to_have_text(str(before + 1))
    # 危險網址被拒
    page.get_by_test_id("link-dest").fill("javascript:alert(1)")
    page.get_by_test_id("link-create").click()
    expect(page.locator(".inline-error").first).to_contain_text("http/https")
    # 圖表與卡片一致 + 時間範圍切換
    page.get_by_test_id("range-14").click()
    page.wait_for_timeout(500)
    bars = page.get_by_test_id("bars-clicks").locator(".bar span").all_inner_texts()
    assert sum(int(x) for x in bars) == int(page.get_by_test_id("card-clicks").inner_text())
    page.get_by_test_id("range-1").click()
    page.wait_for_timeout(500)
    bars = page.get_by_test_id("bars-clicks").locator(".bar span").all_inner_texts()
    assert sum(int(x) for x in bars) == int(page.get_by_test_id("card-clicks").inner_text())


def test_assistant_scripted_trace_zero_delivery(page):
    goto(page, "assistant")
    expect(page.get_by_text("scripted planner")).to_be_visible()
    page.get_by_test_id("agent-send").click()
    trace = page.get_by_test_id("trace")
    expect(trace).to_be_visible()
    expect(trace).to_contain_text("模擬規劃")
    calls = page.get_by_test_id("tool-call")
    expect(calls.first).to_be_visible()
    assert calls.count() >= 5
    expect(trace).to_contain_text("零份送出")

    # 寫入只能是提案，要 UI 確認
    page.get_by_test_id("agent-input").fill("把 demo_vip01 標記為 Qualified")
    page.get_by_role("button", name="新會話").click()
    page.get_by_test_id("agent-send").click()
    prop = page.get_by_test_id("proposal")
    expect(prop.first).to_contain_text("pending")
    page.get_by_test_id("proposal-confirm").click()
    goto(page, "leads")
    expect(page.get_by_test_id("leads")).to_contain_text("demo_vip01")


def test_empty_and_error_states_are_visible(page):
    goto(page, "pr")
    page.route("**/api/evaluations**", lambda route: route.fulfill(status=500, body='{"error":{"code":"x","message":"模擬後端錯誤"}}', content_type="application/json"))
    page.get_by_test_id("pr-medium").click()
    expect(page.get_by_test_id("error")).to_contain_text("模擬後端錯誤")
    page.unroute("**/api/evaluations**")
    page.get_by_role("button", name="重試").click()
    expect(page.get_by_test_id("error")).to_have_count(0)
