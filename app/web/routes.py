from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import User
from app.services.auth_sessions import get_session_user, revoke_auth_session
from app.services.passkey_reset import (
    create_passkey_reset_token,
    get_user_for_passkey_reset_token,
    set_passkey_reset,
)

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/web/templates")


def _template_auth_context(user: User | None) -> dict[str, bool]:
    return {
        "is_authenticated": user is not None,
        "is_admin": bool(user and user.is_admin),
    }


def _safe_next_path(request: Request) -> str:
    next_path = request.query_params.get("next", "/")
    if not next_path.startswith("/") or next_path.startswith("//"):
        return "/"
    return next_path


async def _get_session_user(request: Request, db: AsyncSession) -> User | None:
    return await get_session_user(request, db)


async def _require_admin_session_user(request: Request, db: AsyncSession) -> User | Response:
    user = await _get_session_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not user.is_admin:
        return RedirectResponse(url="/", status_code=303)
    return user


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    user = await _get_session_user(request, db)
    next_path = _safe_next_path(request)
    if user is not None:
        return RedirectResponse(url=next_path, status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "localhost_hint": request.url.hostname == "127.0.0.1",
            "next_url": next_path,
            **_template_auth_context(None),
        },
    )


@router.post("/logout")
async def logout_page(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    await revoke_auth_session(request, db)
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/", response_class=HTMLResponse, response_model=None)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    user = await _get_session_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if user.is_admin:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html", _template_auth_context(user))


@router.get("/settings", response_class=HTMLResponse, response_model=None)
async def user_settings(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    user = await _get_session_user(request, db)
    if user is None:
        return RedirectResponse(url="/login?next=/settings", status_code=303)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            **_template_auth_context(user),
            "email": user.email,
            "display_name": user.display_name,
        },
    )


@router.get("/lists/{list_id}", response_class=HTMLResponse, response_model=None)
async def list_detail(
    request: Request, list_id: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await _get_session_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if user.is_admin:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(
        request,
        "list_detail.html",
        {
            "list_id": list_id,
            **_template_auth_context(user),
        },
    )


@router.get("/invite/{token}", response_class=HTMLResponse, response_model=None)
async def invite_detail(
    request: Request, token: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await _get_session_user(request, db)
    if user is None:
        return RedirectResponse(url=f"/login?next=/invite/{token}", status_code=303)
    if user.is_admin:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(
        request,
        "invite_detail.html",
        {
            "invite_token": token,
            **_template_auth_context(user),
        },
    )


@router.get("/admin/passkey-reset-links", response_class=HTMLResponse, response_model=None)
async def admin_passkey_reset_links(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Response:
    admin_user = await _require_admin_session_user(request, db)
    if isinstance(admin_user, Response):
        return admin_user
    return templates.TemplateResponse(
        request,
        "admin_passkey_reset_links.html",
        {
            **_template_auth_context(admin_user),
            "generated_link": None,
            "generated_email": None,
            "error_message": None,
        },
    )


@router.post("/admin/passkey-reset-links", response_class=HTMLResponse, response_model=None)
async def create_admin_passkey_reset_link(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> Response:
    admin_user = await _require_admin_session_user(request, db)
    if isinstance(admin_user, Response):
        return admin_user

    normalized_email = email.strip().casefold()
    result = await db.execute(select(User).where(User.email.ilike(normalized_email)))
    user = result.scalar_one_or_none()
    if user is None:
        return templates.TemplateResponse(
            request,
            "admin_passkey_reset_links.html",
            {
                **_template_auth_context(admin_user),
                "generated_link": None,
                "generated_email": email.strip(),
                "error_message": "No account found for that email address.",
            },
            status_code=404,
        )

    token = create_passkey_reset_token()
    set_passkey_reset(user, token)
    await db.commit()
    reset_link = str(request.base_url).rstrip("/") + f"/passkey-reset/{token}"
    return templates.TemplateResponse(
        request,
        "admin_passkey_reset_links.html",
        {
            **_template_auth_context(admin_user),
            "generated_link": reset_link,
            "generated_email": user.email,
            "error_message": None,
        },
    )


@router.get("/passkey-reset/{token}", response_class=HTMLResponse, response_model=None)
async def passkey_reset_page(
    request: Request, token: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await get_user_for_passkey_reset_token(db, token)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    session_user = await _get_session_user(request, db)
    return templates.TemplateResponse(
        request,
        "passkey_reset.html",
        {
            **_template_auth_context(session_user),
            "email": user.email,
            "display_name": user.display_name,
            "token": token,
        },
    )
