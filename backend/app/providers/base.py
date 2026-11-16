"""Provider 介面。Demo 與 Live 共用同一組資料結構，domain service 不知道背後是誰。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field

from ..schemas import Intent, Risk


class Classification(BaseModel):
    """分類結果（Live AI 輸出會用這個 model 驗證）。risk 是建議等級，不是校準過的機率。"""
    relevant: bool
    intent: Intent
    risk: Risk
    reason: str = Field(min_length=1, max_length=400)
    evidence: str = Field(default="", max_length=300)
    flags: list[str] = []


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class AgentTurn:
    text: str
    tool_uses: list[ToolUse] = field(default_factory=list)
    stop_reason: str = "end_turn"   # end_turn | tool_use | max_tokens
    usage: dict[str, int] | None = None  # Live 才有；Demo 為 None（只計模擬 units）
    raw_blocks: list[dict] = field(default_factory=list)  # 原樣 assistant content blocks（保留 call id）


class AIProvider(Protocol):
    name: str          # "demo" | "anthropic"
    label: str         # 給 UI 如實顯示

    def classify(self, post_text: str, project: dict) -> Classification: ...
    def draft(self, post: dict, brand: dict, evaluation: dict) -> str: ...
    def agent_turn(self, messages: list[dict], tools: list[dict], system: str) -> AgentTurn: ...


class SocialProvider(Protocol):
    name: str

    def search_posts(self, conn, keywords: list[str], since: str, until: str, sort: str, limit: int) -> list[dict]: ...
    def list_comments(self, conn, post_id: str) -> list[dict]: ...


class DeliveryProvider(Protocol):
    def simulate_delivery(self, kind: str, injected: str) -> "DeliveryOutcome": ...


@dataclass
class DeliveryOutcome:
    status: str                # simulated_sent | failed_retryable | failed_terminal | unknown
    error: str | None = None
