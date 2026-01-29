"""
User management router: profile, admin operations.
"""
from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentAdminUser, CurrentUser, DbSession
from app.models.user import ApprovalStatus, UserRole
from app.schemas.common import MessageResponse
from app.schemas.user import (
    ApprovalDecision,
    SetRoleRequest,
    TelegramLinkRequest,
    UserAdminResponse,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from app.services.telegram import TelegramService
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["Users"])


# User profile endpoints


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_profile(current_user: CurrentUser) -> UserResponse:
    """Get current authenticated user's profile."""
    return UserResponse.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update user profile",
)
async def update_profile(
    data: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> UserResponse:
    """Update current user's profile."""
    user_service = UserService(db)

    if data.email:
        try:
            current_user = await user_service.update_email(current_user, data.email)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    return UserResponse.model_validate(current_user)


@router.post(
    "/me/telegram",
    response_model=UserResponse,
    summary="Link Telegram account",
)
async def link_telegram(
    data: TelegramLinkRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> UserResponse:
    """Link Telegram chat ID to user account."""
    user_service = UserService(db)

    # Check if chat_id is already linked to another user
    existing = await user_service.get_by_telegram_id(data.tg_chat_id)
    if existing and existing.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This Telegram account is already linked to another user",
        )

    current_user = await user_service.link_telegram(current_user, data.tg_chat_id)
    return UserResponse.model_validate(current_user)


@router.delete(
    "/me/telegram",
    response_model=UserResponse,
    summary="Unlink Telegram account",
)
async def unlink_telegram(
    current_user: CurrentUser,
    db: DbSession,
) -> UserResponse:
    """Unlink Telegram account from user."""
    user_service = UserService(db)
    current_user = await user_service.unlink_telegram(current_user)
    return UserResponse.model_validate(current_user)


# Admin endpoints


@router.get(
    "",
    response_model=UserListResponse,
    summary="List all users (admin)",
)
async def list_users(
    admin: CurrentAdminUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    role: UserRole | None = None,
    approval_status: ApprovalStatus | None = None,
) -> UserListResponse:
    """List all users with pagination and filters. Admin only."""
    user_service = UserService(db)
    users, total = await user_service.list_users(
        page=page,
        per_page=per_page,
        role=role,
        approval_status=approval_status,
    )

    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/pending",
    response_model=list[UserAdminResponse],
    summary="List pending approvals (admin)",
)
async def list_pending(
    admin: CurrentAdminUser,
    db: DbSession,
) -> list[UserAdminResponse]:
    """List users pending approval. Admin only."""
    user_service = UserService(db)
    users = await user_service.list_pending_approval()
    return [UserAdminResponse.model_validate(u) for u in users]


@router.get(
    "/{user_id}",
    response_model=UserAdminResponse,
    summary="Get user by ID (admin)",
)
async def get_user(
    user_id: int,
    admin: CurrentAdminUser,
    db: DbSession,
) -> UserAdminResponse:
    """Get user details by ID. Admin only."""
    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserAdminResponse.model_validate(user)


@router.post(
    "/{user_id}/approve",
    response_model=UserResponse,
    summary="Approve or deny user (admin)",
)
async def approve_user(
    user_id: int,
    data: ApprovalDecision,
    admin: CurrentAdminUser,
    db: DbSession,
) -> UserResponse:
    """Approve or deny a pending user. Admin only."""
    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    telegram = TelegramService()

    if data.approve:
        user = await user_service.approve_user(user, admin.id, data.note)

        # Notify user via Telegram if linked
        if user.tg_chat_id:
            await telegram.notify_user_approved(user.tg_chat_id)
    else:
        user = await user_service.deny_user(user, admin.id, data.note)

        # Notify user via Telegram if linked
        if user.tg_chat_id:
            await telegram.notify_user_denied(user.tg_chat_id, data.note)

    return UserResponse.model_validate(user)


@router.post(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Set user role (admin)",
)
async def set_user_role(
    user_id: int,
    data: SetRoleRequest,
    admin: CurrentAdminUser,
    db: DbSession,
) -> UserResponse:
    """Change user's role. Admin only."""
    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent demoting self
    if user.id == admin.id and data.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote yourself",
        )

    user = await user_service.set_role(user, data.role)
    return UserResponse.model_validate(user)


@router.post(
    "/{user_id}/premium",
    response_model=UserResponse,
    summary="Grant premium (admin)",
)
async def grant_premium(
    user_id: int,
    admin: CurrentAdminUser,
    db: DbSession,
    days: int = Query(30, ge=1, le=365),
) -> UserResponse:
    """Grant premium subscription to user. Admin only."""
    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user = await user_service.grant_premium(user, days)

    # Notify user
    if user.tg_chat_id:
        telegram = TelegramService()
        await telegram.notify_premium_activated(user.tg_chat_id, days)

    return UserResponse.model_validate(user)


@router.delete(
    "/{user_id}/premium",
    response_model=UserResponse,
    summary="Revoke premium (admin)",
)
async def revoke_premium(
    user_id: int,
    admin: CurrentAdminUser,
    db: DbSession,
) -> UserResponse:
    """Revoke premium subscription from user. Admin only."""
    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user = await user_service.revoke_premium(user)
    return UserResponse.model_validate(user)


@router.post(
    "/{user_id}/deactivate",
    response_model=MessageResponse,
    summary="Deactivate user (admin)",
)
async def deactivate_user(
    user_id: int,
    admin: CurrentAdminUser,
    db: DbSession,
) -> MessageResponse:
    """Deactivate a user account. Admin only."""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself",
        )

    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await user_service.deactivate_user(user)
    return MessageResponse(message="User deactivated")


@router.post(
    "/{user_id}/activate",
    response_model=MessageResponse,
    summary="Activate user (admin)",
)
async def activate_user(
    user_id: int,
    admin: CurrentAdminUser,
    db: DbSession,
) -> MessageResponse:
    """Reactivate a deactivated user. Admin only."""
    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await user_service.activate_user(user)
    return MessageResponse(message="User activated")
