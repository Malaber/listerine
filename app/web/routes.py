from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_list_for_user
from app.core.database import get_db
from app.models import User
from app.services.auth_sessions import get_session_user, revoke_auth_session
from app.services.passkey_reset import get_user_for_passkey_reset_token

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/web/templates")
static_root = Path("app/web/static")


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


async def _last_list_redirect(
    request: Request, db: AsyncSession, user: User
) -> RedirectResponse | None:
    last_list_id = request.session.get("last_list_id")
    if not isinstance(last_list_id, str):
        return None

    try:
        parsed_list_id = UUID(last_list_id)
        await get_list_for_user(db, parsed_list_id, user.id)
    except (ValueError, HTTPException):
        request.session.pop("last_list_id", None)
        return None

    return RedirectResponse(url=f"/lists/{parsed_list_id}", status_code=303)


@router.get("/manifest.webmanifest", include_in_schema=False)
async def web_manifest() -> FileResponse:
    return FileResponse(
        static_root / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@router.get("/service-worker.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    return FileResponse(
        static_root / "service-worker.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


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
    if request.query_params.get("dashboard") != "1":
        last_list_redirect = await _last_list_redirect(request, db, user)
        if last_list_redirect is not None:
            return last_list_redirect
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
    try:
        request.session["last_list_id"] = str(UUID(list_id))
    except ValueError:
        request.session.pop("last_list_id", None)
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


@router.get("/passkey-add/{token}", response_class=HTMLResponse, response_model=None)
async def passkey_add_page(
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
