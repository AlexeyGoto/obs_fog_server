"""
Common schemas used across the application.
"""
from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class ErrorResponse(BaseModel):
    """Error response schema."""

    detail: str
    code: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str
    environment: str


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(default=1, ge=1, description="Page number")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        """Calculate offset for database query."""
        return (self.page - 1) * self.per_page
