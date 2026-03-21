from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models import User

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/web/templates")


def _template_auth_context(user: User | None) -> dict[str, bool]:
    return {
        "is_authenticated": user is not None,
        "is_admin": bool(user and user.is_admin),
    }


def _has_session_access_token(request: Request) -> bool:
    raw_token = request.session.get("access_token")
    if not raw_token:
        return False
    try:
        payload = jwt.decode(raw_token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return False
    return bool(payload.get("sub"))


def _safe_next_path(request: Request) -> str:
    next_path = request.query_params.get("next", "/")
    if not next_path.startswith("/") or next_path.startswith("//"):
        return "/"
    return next_path


async def _get_session_user(request: Request, db: AsyncSession) -> User | None:
    raw_token = request.session.get("access_token")
    if not raw_token:
        return None

    try:
        payload = jwt.decode(raw_token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise JWTError("Missing user subject")
        user_uuid = UUID(user_id)
    except (JWTError, ValueError):
        request.session.clear()
        return None

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        request.session.clear()
        return None
    return user


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    user = await _get_session_user(request, db)
    next_path = _safe_next_path(request)
    if user is not None:
        return RedirectResponse(url=next_path, status_code=303)
    localhost_hint = request.url.hostname == "127.0.0.1"
    return templates.TemplateResponse(
        request,
        "login.html",
        {"localhost_hint": localhost_hint, "next_url": next_path, **_template_auth_context(None)},
    )


@router.post("/logout")
async def logout_page(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/", response_class=HTMLResponse, response_model=None)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    user = await _get_session_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html", _template_auth_context(user))


@router.get("/lists/{list_id}", response_class=HTMLResponse, response_model=None)
async def list_detail(
    request: Request, list_id: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await _get_session_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "list_detail.html",
        {
            "list_id": list_id,
            **_template_auth_context(user),
            "access_token": request.session.get("access_token", ""),
        },
    )


@router.get("/invite/{token}", response_class=HTMLResponse, response_model=None)
async def invite_detail(
    request: Request, token: str, db: AsyncSession = Depends(get_db)
) -> Response:
    user = await _get_session_user(request, db)
    if user is None:
        return RedirectResponse(url=f"/login?next=/invite/{token}", status_code=303)
    return templates.TemplateResponse(
        request,
        "invite_detail.html",
        {
            "invite_token": token,
            **_template_auth_context(user),
        },
    )
