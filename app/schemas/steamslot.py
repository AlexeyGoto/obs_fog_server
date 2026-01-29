"""
SteamSlot schemas for account and lease management.
"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.steamslot import LeaseStatus


class SteamAccountBase(BaseModel):
    """Base Steam account schema."""

    name: str = Field(..., min_length=1, max_length=100, description="Account name")
    max_slots: int = Field(default=1, ge=1, le=10, description="Max concurrent slots")
    enabled: bool = Field(default=True, description="Whether account is enabled")


class SteamAccountCreate(SteamAccountBase):
    """Schema for creating Steam account."""

    notes: str | None = Field(None, max_length=1000, description="Admin notes")


class SteamAccountUpdate(BaseModel):
    """Schema for updating Steam account."""

    name: str | None = Field(None, min_length=1, max_length=100)
    max_slots: int | None = Field(None, ge=1, le=10)
    enabled: bool | None = None
    notes: str | None = Field(None, max_length=1000)


class SteamAccountResponse(SteamAccountBase):
    """Steam account response."""

    id: int
    has_file: bool
    file_name: str | None
    file_encrypted: bool
    file_updated_at: datetime | None
    active_lease_count: int
    available_slots: int
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SteamAccountListResponse(BaseModel):
    """List of Steam accounts."""

    items: list[SteamAccountResponse]
    total: int


# Steam Lease Schemas


class SteamLeaseCreate(BaseModel):
    """Schema for creating a lease."""

    account_id: int = Field(..., description="Steam account ID")
    pc_id: int = Field(..., description="PC ID to assign")
    duration_hours: int = Field(
        default=24, ge=1, le=168, description="Lease duration in hours"
    )


class SteamLeaseResponse(BaseModel):
    """Steam lease response."""

    id: int
    account_id: int
    account_name: str
    pc_id: int
    pc_name: str
    token: str
    status: LeaseStatus
    expires_at: datetime
    released_at: datetime | None
    message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SteamLeaseListResponse(BaseModel):
    """List of Steam leases."""

    items: list[SteamLeaseResponse]
    total: int


# File Upload


class FileUploadResponse(BaseModel):
    """File upload response."""

    success: bool
    file_name: str
    file_size: int
    sha256: str
    encrypted: bool
