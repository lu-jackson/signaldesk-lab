"""Pydantic 請求／資料模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Platform = Literal["threads", "x", "instagram", "facebook"]
Mode = Literal["manual_review", "observe_only", "auto_simulate"]
Intent = Literal["seeking", "advice", "promotion", "complaint", "other"]
Risk = Literal["low", "medium", "high"]


class BrandData(BaseModel):
    intro: str = ""
    products: list[str] = []
    audience: str = ""
    service_area: str = ""
    tone: str = ""
    faq: list[dict[str, str]] = []  # [{"q":..., "a":...}]
    facts: list[str] = []           # 可確認事實：草稿只能引用這些
    forbidden: list[str] = []       # 不可承諾事項
    cta: str = ""


class BrandIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    data: BrandData = BrandData()


class AccountIn(BaseModel):
    platform: Platform
    handle: str = Field(pattern=r"^demo_[a-z0-9_]{1,30}$")
    display_name: str = Field(min_length=1, max_length=60)
    brand_id: str | None = None


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    brand_id: str
    account_id: str
    purpose: str = ""
    keywords: list[str] = Field(min_length=1)
    must_terms: list[str] = []
    exclude_terms: list[str] = []
    window_days: int = Field(default=7, ge=1, le=90)
    mode: Mode = "manual_review"
    daily_limit: int = Field(default=5, ge=0, le=100)
    schedule_enabled: bool = False
    interval_seconds: int = Field(default=3600, ge=60)
    enabled: bool = True

    @field_validator("keywords", "must_terms", "exclude_terms")
    @classmethod
    def _clean(cls, v):
        return [s.strip() for s in v if s and s.strip()]


class DraftEdit(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class DraftGenerate(BaseModel):
    project_id: str
    post_id: str


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    post_id: str
    keywords: list[str] = Field(min_length=1)
    reply_template: str = Field(min_length=1, max_length=500)
    send_dm: bool = False
    dm_template: str = ""
    links: list[str] = Field(default=[], max_length=3)
    enabled: bool = True


class CommentEventIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    post_id: str
    author_handle: str = Field(pattern=r"^demo_[a-z0-9_]{1,30}$")
    text: str = Field(min_length=1, max_length=500)


class InjectIn(BaseModel):
    channel: Literal["public_reply", "dm", "draft_reply"]
    outcome: Literal["none", "success", "permission_revoked", "rate_limit", "terminal_failure", "unknown"]


class LeadIn(BaseModel):
    platform: Platform
    handle: str = Field(min_length=1, max_length=60)
    post_id: str | None = None
    reason: str = Field(min_length=1, max_length=300)


class LeadPatch(BaseModel):
    status: Literal["New", "Qualified", "Ignored", "Converted"] | None = None
    note: str | None = Field(default=None, max_length=1000)


class LinkIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    destination: str


class SettingsPatch(BaseModel):
    social_source: Literal["demo", "threads_readonly"] | None = None
    ai_provider: Literal["demo", "anthropic"] | None = None


class AgentMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class SessionIn(BaseModel):
    title: str = "新會話"


class PostImportIn(BaseModel):
    """手動貼上一則「你自己看到的公開貼文」。作者帳號與網址都可留空；不要貼私訊或含個資的內容。"""
    project_id: str
    text: str = Field(min_length=1, max_length=1500)
    platform: Platform = "threads"
    author_handle: str = Field(default="", max_length=40)   # 第三方帳號名稱屬個資，預設留空
    source_url: str = Field(default="", max_length=500)

    @field_validator("source_url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        v = v.strip()
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("來源網址必須以 http:// 或 https:// 開頭")
        return v

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("貼文內容不可為空白")
        return v
