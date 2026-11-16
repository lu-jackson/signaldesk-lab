"""可注入的時鐘：所有「現在」都從這裡取，測試可凍結時間。"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

_fixed: datetime | None = None
FMT = "%Y-%m-%dT%H:%M:%SZ"


def now() -> datetime:
    if _fixed is not None:
        return _fixed
    env = os.environ.get("SIGNALDESK_FIXED_NOW")
    if env:
        return parse(env)
    return datetime.now(timezone.utc).replace(microsecond=0)


def set_fixed(value: datetime | str | None) -> None:
    global _fixed
    _fixed = parse(value) if isinstance(value, str) else value


def advance(**kw) -> None:
    global _fixed
    _fixed = now() + timedelta(**kw)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).astimezone(timezone.utc).strftime(FMT)


def parse(s: str) -> datetime:
    return datetime.strptime(s, FMT).replace(tzinfo=timezone.utc)


def now_iso() -> str:
    return iso(now())
