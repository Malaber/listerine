from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import User
from app.services.auth_sessions import get_session_user, revoke_auth_session

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
