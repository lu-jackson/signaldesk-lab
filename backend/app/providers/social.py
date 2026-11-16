"""Social providers。

DemoSocial：查本機 SQLite 合成資料（關鍵字 + 時間；不是向量語意搜尋）。
ThreadsReadonlyProvider：只有讀取方法。沒有 write method，繼承後也不會意外可送出。
SimulatedDelivery：唯一的「投遞」實作，只回報本機模擬結果，不連任何網路。
"""
from __future__ import annotations

from typing import Callable

import httpx

from .. import config
from ..errors import DependencyError, NotConfigured
from .base import DeliveryOutcome


class DemoSocial:
    name = "demo"

    def search_posts(self, conn, keywords, since, until, sort, limit):
        if not keywords:
            return []
        likes = " OR ".join(["text LIKE ?"] * len(keywords))
        order = "(likes + replies*2) DESC, created_at DESC" if sort == "hot" else "created_at DESC"
        cur = conn.execute(
            f"SELECT * FROM source_posts WHERE is_own=0 AND created_at>=? AND created_at<? AND ({likes}) ORDER BY {order} LIMIT ?",
            (since, until, *[f"%{k}%" for k in keywords], limit))
        return [dict(r) for r in cur]

    def list_comments(self, conn, post_id):
        return [dict(r) for r in conn.execute("SELECT * FROM comments WHERE post_id=? ORDER BY created_at", (post_id,))]


class ThreadsReadonlyProvider:
    """依 Threads 官方 keyword_search 文件實作的唯讀 adapter（https://developers.facebook.com/documentation/threads/keyword-search）。

    重要：本專案沒有已授權的 token/權限，所以這段從未對真實 Threads 驗證過；僅用 httpx.MockTransport 測錯誤處理與分頁。
    需要 threads_basic + threads_keyword_search 權限的 access token。
    """
    name = "threads_readonly"
    BASE = "https://graph.threads.net"

    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None):
        self._token = token
        self._transport = transport

    @property
    def token(self) -> str:
        t = self._token or config.threads_token()
        if not t:
            raise NotConfigured("Threads 唯讀搜尋未配置：缺少 THREADS_ACCESS_TOKEN。此能力標示為「未配置／未實測」。")
        return t

    def search_posts(self, conn, keywords, since, until, sort, limit):
        token = self.token
        out: list[dict] = []
        with httpx.Client(transport=self._transport, timeout=15) as c:
            for kw in keywords:
                cursor = None
                while len(out) < limit:
                    params = {"q": kw, "search_type": "TOP" if sort == "hot" else "RECENT",
                              "fields": "id,text,username,timestamp,like_count,reply_count",
                              "since": since, "until": until, "access_token": token}
                    if cursor:
                        params["after"] = cursor
                    try:
                        r = c.get(f"{self.BASE}/keyword_search", params=params)
                    except httpx.HTTPError as e:
                        raise DependencyError(f"Threads 連線失敗：{type(e).__name__}") from e
                    if r.status_code == 401:
                        raise DependencyError("Threads token 無效或過期（401）", "threads_unauthorized")
                    if r.status_code == 403:
                        raise DependencyError("Threads 權限不足（403）：需要 threads_keyword_search", "threads_forbidden")
                    if r.status_code == 429:
                        raise DependencyError("Threads rate limit（429），請稍後重試", "threads_rate_limited")
                    if r.status_code >= 400:
                        raise DependencyError(f"Threads 回應錯誤 {r.status_code}")
                    body = r.json()
                    for p in body.get("data", []):
                        if not p.get("text"):
                            continue
                        out.append({"id": f"threads_{p['id']}", "platform": "threads", "author_handle": p.get("username", "unknown"),
                                    "text": p["text"], "created_at": _to_z(p.get("timestamp", "")), "likes": p.get("like_count", 0),
                                    "replies": p.get("reply_count", 0), "is_own": 0, "own_account_id": None, "synthetic": 0})
                    cursor = (body.get("paging") or {}).get("cursors", {}).get("after")
                    if not cursor or not body.get("data"):
                        break
        seen, uniq = set(), []
        for p in out:
            if p["id"] not in seen:
                seen.add(p["id"])
                uniq.append(p)
        return uniq[:limit]

    def list_comments(self, conn, post_id):
        raise NotConfigured("Threads 留言讀取未實作於本專案（僅關鍵字搜尋）")


def _to_z(ts: str) -> str:
    # "2026-11-10T08:00:00+0000" → "2026-11-10T08:00:00Z"
    return ts[:19] + "Z" if len(ts) >= 19 else ts


class SimulatedDelivery:
    """注入結果對應：none/success → 成功；rate_limit → 可重試；permission_revoked/terminal_failure → 終局失敗；unknown → 結果不明。"""

    def simulate_delivery(self, kind: str, injected: str) -> DeliveryOutcome:
        if injected in ("none", "success"):
            return DeliveryOutcome("simulated_sent")
        if injected == "rate_limit":
            return DeliveryOutcome("failed_retryable", "模擬平台 rate limit")
        if injected == "permission_revoked":
            return DeliveryOutcome("failed_terminal", "模擬：授權已失效（permission_revoked）")
        if injected == "terminal_failure":
            return DeliveryOutcome("failed_terminal", "模擬：終局失敗（例如對方已封鎖）")
        if injected == "unknown":
            return DeliveryOutcome("unknown", "模擬：平台逾時，結果未知")
        raise ValueError(injected)


def get_social(conn) -> "DemoSocial | ThreadsReadonlyProvider":
    from ..services import settings
    return ThreadsReadonlyProvider() if settings.get(conn, "social_source") == "threads_readonly" else DemoSocial()


def get_ai(conn):
    from ..services import settings
    from .ai_anthropic import AnthropicAI
    from .ai_demo import DemoAI
    if _ai_override is not None and settings.get(conn, "ai_provider") == "anthropic":
        return _ai_override()
    return AnthropicAI() if settings.get(conn, "ai_provider") == "anthropic" else DemoAI()


_ai_override: Callable | None = None
