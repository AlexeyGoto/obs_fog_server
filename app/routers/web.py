"""
Web routes for HTML templates.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.deps import OptionalUser, CurrentUser
from app.models.user import User

router = APIRouter(tags=["Web"])

templates = Jinja2Templates(directory="app/templates")


def render(request: Request, template: str, context: dict = None, user: User = None):
    """Helper to render templates with common context."""
    ctx = {
        "request": request,
        "user": user,
        "messages": [],  # Can be extended for flash messages
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(template, ctx)


# Public pages
@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: OptionalUser):
    """Home page."""
    return render(request, "pages/index.html", user=user)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user: OptionalUser):
    """Login page."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return render(request, "auth/login.html", user=user)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user: OptionalUser):
    """Registration page."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return render(request, "auth/register.html", user=user)


def requires_telegram_redirect(user: User) -> bool:
    """Check if user needs to complete Telegram binding."""
    if not settings.telegram_required:
        return False
    # User needs to bind Telegram if: not approved AND no tg_chat_id
    return not user.is_approved and not user.tg_chat_id


# Telegram pending page
@router.get("/pending", response_class=HTMLResponse)
async def pending_telegram_page(request: Request, user: CurrentUser):
    """Page showing instructions to link Telegram."""
    if user.is_approved or (user.tg_chat_id and not settings.approval_required):
        return RedirectResponse(url="/dashboard", status_code=302)
    return render(
        request,
        "pages/pending_telegram.html",
        {"bot_username": settings.telegram_bot_username},
        user=user,
    )


# Protected pages
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, user: CurrentUser):
    """Dashboard page (requires auth)."""
    if requires_telegram_redirect(user):
        return RedirectResponse(url="/pending", status_code=302)
    return render(request, "pages/dashboard.html", user=user)


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user: CurrentUser):
    """Profile settings page (requires auth)."""
    if requires_telegram_redirect(user):
        return RedirectResponse(url="/pending", status_code=302)
    return render(request, "pages/profile.html", user=user)


@router.get("/pcs/{pc_id}", response_class=HTMLResponse)
async def pc_detail_page(request: Request, pc_id: int, user: CurrentUser):
    """PC detail page (requires auth)."""
    if requires_telegram_redirect(user):
        return RedirectResponse(url="/pending", status_code=302)
    return render(request, "pages/pc_detail.html", {"pc_id": pc_id}, user=user)


@router.get("/steamslot", response_class=HTMLResponse)
async def steamslot_page(request: Request, user: CurrentUser):
    """Steam Slot management page (requires auth)."""
    if requires_telegram_redirect(user):
        return RedirectResponse(url="/pending", status_code=302)
    return render(request, "pages/steamslot.html", user=user)


@router.get("/premium", response_class=HTMLResponse)
async def premium_page(request: Request, user: CurrentUser):
    """Premium subscription page (requires auth)."""
    if requires_telegram_redirect(user):
        return RedirectResponse(url="/pending", status_code=302)
    return render(request, "pages/premium.html", user=user)


# Admin pages
@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user: CurrentUser):
    """Admin dashboard (requires admin role)."""
    if user.role.value != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)
    return render(request, "admin/dashboard.html", user=user)


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, user: CurrentUser):
    """Admin users management (requires admin role)."""
    if user.role.value != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)
    return render(request, "admin/users.html", user=user)


@router.get("/admin/pending", response_class=HTMLResponse)
async def admin_pending_page(request: Request, user: CurrentUser):
    """Admin pending approvals (requires admin role)."""
    if user.role.value != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)
    return render(request, "admin/pending.html", user=user)
