"""
Authentication and authorization schemas.
"""
from pydantic import BaseModel, EmailStr, Field


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: int
    type: str
    exp: int
    iat: int


class LoginRequest(BaseModel):
    """Login request schema."""

    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=6, description="User password")


class RegisterRequest(BaseModel):
    """Registration request schema."""

    email: EmailStr = Field(..., description="User email")
    password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Password (min 8 characters)",
    )
    password_confirm: str = Field(..., description="Password confirmation")

    def passwords_match(self) -> bool:
        """Check if passwords match."""
        return self.password == self.password_confirm


class PasswordChangeRequest(BaseModel):
    """Password change request schema."""

    current_password: str = Field(..., description="Current password")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="New password (min 8 characters)",
    )
    new_password_confirm: str = Field(..., description="New password confirmation")

    def passwords_match(self) -> bool:
        """Check if new passwords match."""
        return self.new_password == self.new_password_confirm


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""

    refresh_token: str = Field(..., description="Refresh token")
