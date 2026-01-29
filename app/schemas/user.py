"""
User schemas for API requests and responses.
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import ApprovalStatus, UserRole


class UserBase(BaseModel):
    """Base user schema with common fields."""

    email: EmailStr


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(..., min_length=8, max_length=100)


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    email: EmailStr | None = None


class UserResponse(UserBase):
    """User response schema (public info)."""

    id: int
    role: UserRole
    is_active: bool
    is_approved: bool
    is_premium: bool
    approval_status: ApprovalStatus
    tg_chat_id: int | None = None
    premium_until: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserAdminResponse(UserResponse):
    """Extended user response for admin."""

    approval_requested_at: datetime | None = None
    approval_decided_at: datetime | None = None
    approval_decided_by: int | None = None
    approval_note: str | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Paginated list of users."""

    items: list[UserResponse]
    total: int
    page: int
    per_page: int


class ApprovalDecision(BaseModel):
    """Admin approval decision."""

    approve: bool = Field(..., description="True to approve, False to deny")
    note: str | None = Field(None, max_length=500, description="Optional note")


class TelegramLinkRequest(BaseModel):
    """Request to link Telegram account."""

    tg_chat_id: int = Field(..., description="Telegram chat ID")


class SetRoleRequest(BaseModel):
    """Admin request to change user role."""

    role: UserRole = Field(..., description="New user role")
