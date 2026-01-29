"""
PC and streaming session schemas.
"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.pc import ClipStatus, SessionStatus


class PCBase(BaseModel):
    """Base PC schema."""

    name: str = Field(..., min_length=1, max_length=100, description="PC name")


class PCCreate(PCBase):
    """Schema for creating a new PC."""

    pass


class PCUpdate(BaseModel):
    """Schema for updating PC."""

    name: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None


class PCResponse(PCBase):
    """PC response schema."""

    id: int
    user_id: int
    stream_key: str
    is_active: bool
    is_live: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class PCDetailResponse(PCResponse):
    """Detailed PC response with stream URLs."""

    rtmp_url: str
    hls_url: str
    sessions_count: int
    # is_live inherited from PCResponse

    model_config = {"from_attributes": True}


class PCListResponse(BaseModel):
    """List of PCs."""

    items: list[PCResponse]
    total: int


# Stream Session Schemas


class StreamSessionResponse(BaseModel):
    """Stream session response."""

    id: int
    pc_id: int
    started_at: datetime
    ended_at: datetime | None
    status: SessionStatus
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class StreamSessionDetailResponse(StreamSessionResponse):
    """Detailed session response with clip info."""

    clip_status: ClipStatus | None = None
    clip_path: str | None = None
    clip_size_bytes: int | None = None
    clip_error: str | None = None

    model_config = {"from_attributes": True}


class StreamSessionListResponse(BaseModel):
    """List of stream sessions."""

    items: list[StreamSessionResponse]
    total: int


# Clip Job Schemas


class ClipJobResponse(BaseModel):
    """Clip job response."""

    id: int
    session_id: int
    status: ClipStatus
    result_path: str | None
    error: str | None
    size_bytes: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# RTMP Hook Schemas


class RTMPPublishHook(BaseModel):
    """RTMP on_publish hook data."""

    name: str | None = Field(None, description="Stream name (key)")
    key: str | None = Field(None, description="Stream key from query")
    addr: str | None = Field(None, description="Client IP address")
    app: str | None = Field(None, description="Application name")
    tcurl: str | None = Field(None, description="Full RTMP URL")


class RTMPPublishDoneHook(BaseModel):
    """RTMP on_publish_done hook data."""

    name: str | None = Field(None, description="Stream name (key)")
    key: str | None = Field(None, description="Stream key from query")
    addr: str | None = Field(None, description="Client IP address")
    app: str | None = Field(None, description="Application name")
