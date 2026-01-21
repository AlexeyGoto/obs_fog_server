from __future__ import annotations

import datetime as dt
from pydantic import BaseModel, Field


class AcquireRequest(BaseModel):
    pc_name: str = Field(..., min_length=1, max_length=128)
    ttl_seconds: int | None = Field(default=None, ge=30, le=7200)
    account_name: str | None = Field(default=None, max_length=128)


class AcquireResponse(BaseModel):
    ok: bool
    token: str | None = None
    account_name: str | None = None
    expires_at: dt.datetime | None = None
    retry_after_seconds: int | None = None
    message: str | None = None


class HeartbeatRequest(BaseModel):
    token: str = Field(..., min_length=8)
    ttl_seconds: int | None = Field(default=None, ge=30, le=7200)


class ReleaseRequest(BaseModel):
    token: str = Field(..., min_length=8)
    status: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=2000)


class SimpleOk(BaseModel):
    ok: bool
    message: str | None = None
