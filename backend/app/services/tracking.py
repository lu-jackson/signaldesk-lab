"""追蹤連結與分析。

* 目的地只能在「建立連結」時由使用者設定並驗證（http/https、主機在允許清單、不含帳密）；
  `/t/{token}` 的 request 完全不能指定導向目標 → 不是 open redirect。
* unique 只用隨機 session cookie 估算（estimated unique），不做裝置指紋。
* 分析使用半開區間 [from, to)；沒有分母時回 null，不偽裝成 0%。
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from .. import clock, config
from ..db import new_id, row, rows, tx
from ..errors import DomainError, NotFound
from ..schemas import LinkIn

BOT_RE = re.compile(r"bot|crawler|spider|curl|wget|headless|python-requests|httpx|preview", re.I)


def validate_destination(url: str) -> str:
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https"):
        raise DomainError("目的網址只接受 http/https", "invalid_destination")
    if not p.hostname:
        raise DomainError("目的網址缺少主機", "invalid_destination")
    if p.username or p.password:
        raise DomainError("目的網址不可含帳密", "invalid_destination")
    if p.hostname.lower() not in config.tracking_allowed_hosts():
        raise DomainError(f"目的主機 {p.hostname} 不在允許清單（TRACKING_ALLOWED_HOSTS）", "destination_not_allowed")
    return url.strip()


def create_link(conn, body: LinkIn) -> dict:
    dest = validate_destination(body.destination)
    lid, tok = new_id("lnk"), secrets.token_urlsafe(6)
    with tx(conn):
        conn.execute("INSERT INTO tracking_links(id,token,label,destination,created_at) VALUES(?,?,?,?,?)", (lid, tok, body.label, dest, clock.now_iso()))
    return get_link(conn, lid)


def get_link(conn, lid: str) -> dict:
    r = row(conn.execute("SELECT * FROM tracking_links WHERE id=?", (lid,)).fetchone())
    if not r:
        raise NotFound("找不到追蹤連結")
    r["short_url"] = f"{config.base_url()}/t/{r['token']}"
    return r


def list_links(conn) -> list[dict]:
    out = rows(conn.execute("SELECT l.*, (SELECT COUNT(*) FROM click_events c WHERE c.link_id=l.id AND c.is_bot=0) clicks, "
                            "(SELECT COUNT(DISTINCT session_id) FROM click_events c WHERE c.link_id=l.id AND c.is_bot=0) estimated_unique "
                            "FROM tracking_links l ORDER BY created_at DESC, rowid DESC"))
    for r in out:
        r["short_url"] = f"{config.base_url()}/t/{r['token']}"
    return out


def record_click(conn, token: str, user_agent: str, session_id: str | None) -> tuple[str, str]:
    """回傳 (destination, session_id)。destination 一律取自 DB。"""
    link = row(conn.execute("SELECT * FROM tracking_links WHERE token=? AND active=1", (token,)).fetchone())
    if not link:
        raise NotFound("連結不存在或已停用")
    sid = session_id if session_id and re.fullmatch(r"[A-Za-z0-9_-]{8,64}", session_id) else secrets.token_urlsafe(12)
    ua = user_agent or ""
    device = "bot" if BOT_RE.search(ua) else ("mobile" if re.search(r"mobile|android|iphone", ua, re.I) else ("desktop" if ua else "unknown"))
    with tx(conn):
        conn.execute("INSERT INTO click_events(id,link_id,session_id,is_bot,device,country,synthetic,clicked_at) VALUES(?,?,?,?,?,NULL,0,?)",
                     (new_id("clk"), link["id"], sid, int(bool(BOT_RE.search(ua))), device, clock.now_iso()))
    return link["destination"], sid


def _range(frm: str | None, to: str | None, default_days: int = 7) -> tuple[str, str]:
    end = to or clock.now_iso()
    start = frm or clock.iso(clock.parse(end) - timedelta(days=default_days))
    try:
        clock.parse(start), clock.parse(end)
    except ValueError:
        raise DomainError("時間格式必須為 YYYY-MM-DDTHH:MM:SSZ")
    if start >= end:
        raise DomainError("from 必須早於 to（半開區間 [from, to)）")
    return start, end


def _rate(num: int, den: int):
    return None if den == 0 else round(num / den, 4)


def summary(conn, frm: str | None = None, to: str | None = None, link_id: str | None = None) -> dict:
    start, end = _range(frm, to)
    cl_where, cl_p = "WHERE clicked_at>=? AND clicked_at<?", [start, end]
    if link_id:
        cl_where += " AND link_id=?"
        cl_p.append(link_id)
    q = lambda sql, p: conn.execute(sql, p).fetchone()[0]
    sent = q("SELECT COUNT(*) FROM delivery_attempts WHERE status='simulated_sent' AND updated_at>=? AND updated_at<?", [start, end])
    accepted = q("SELECT COUNT(*) FROM delivery_attempts WHERE created_at>=? AND created_at<?", [start, end])
    unknown = q("SELECT COUNT(*) FROM delivery_attempts WHERE status='unknown' AND created_at>=? AND created_at<?", [start, end])
    clicks = q(f"SELECT COUNT(*) FROM click_events {cl_where} AND is_bot=0", cl_p)
    bots = q(f"SELECT COUNT(*) FROM click_events {cl_where} AND is_bot=1", cl_p)
    uniq = q(f"SELECT COUNT(DISTINCT session_id) FROM click_events {cl_where} AND is_bot=0", cl_p)
    synth = q(f"SELECT COUNT(*) FROM click_events {cl_where} AND synthetic=1", cl_p)
    days: dict[str, dict] = {}
    d0 = clock.parse(start).date()
    d1 = (clock.parse(end) - timedelta(seconds=1)).date()
    for i in range((d1 - d0).days + 1):
        days[(d0 + timedelta(days=i)).isoformat()] = {"day": (d0 + timedelta(days=i)).isoformat(), "clicks": 0, "estimated_unique": 0, "simulated_sent": 0}
    for r in conn.execute(f"SELECT substr(clicked_at,1,10) d, COUNT(*) c, COUNT(DISTINCT session_id) u FROM click_events {cl_where} AND is_bot=0 GROUP BY d", cl_p):
        if r["d"] in days:
            days[r["d"]].update(clicks=r["c"], estimated_unique=r["u"])
    for r in conn.execute("SELECT substr(updated_at,1,10) d, COUNT(*) c FROM delivery_attempts WHERE status='simulated_sent' AND updated_at>=? AND updated_at<? GROUP BY d", (start, end)):
        if r["d"] in days:
            days[r["d"]]["simulated_sent"] = r["c"]
    devices = rows(conn.execute(f"SELECT device, COUNT(*) c, MAX(synthetic) synthetic FROM click_events {cl_where} AND is_bot=0 GROUP BY device", cl_p))
    return {
        "period": {"from": start, "to": end, "interval": "[from, to)"},
        "generated_at": clock.now_iso(),
        "has_data": bool(accepted or clicks or bots),
        "api_accepted": accepted, "simulated_sent": sent, "unknown_delivery": unknown,
        "clicks": clicks, "bot_clicks": bots, "estimated_unique": uniq,
        "synthetic_clicks": synth,
        "click_per_simulated_send": _rate(clicks, sent),
        "denominators": {"click_per_simulated_send": sent},
        "series": list(days.values()),
        "devices": devices,
        "notes": ["simulated_sent = 本機模擬送出，非真實平台送達", "沒有已讀、成交資料（模擬平台不回報）",
                  "estimated_unique 以隨機 session cookie 估算，不是真實人數", "synthetic_clicks 為固定 seed 的合成點擊"],
    }


def engagement(conn, frm: str | None = None, to: str | None = None) -> dict:
    start, end = _range(frm, to, 14)
    items = rows(conn.execute("SELECT day, SUM(impressions) impressions, SUM(likes) likes, COUNT(DISTINCT post_id) posts FROM engagement_snapshots "
                              "WHERE day>=substr(?,1,10) AND day<substr(?,1,10) GROUP BY day ORDER BY day", (start, end)))
    return {"synthetic": True, "note": "固定 seed 的合成 engagement snapshots，非即時平台資料", "period": {"from": start, "to": end}, "items": items}
