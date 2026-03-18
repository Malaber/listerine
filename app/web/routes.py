from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.preview import fetch_preview_context

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/web/templates")


def _has_session_access_token(request: Request) -> bool:
    raw_token = request.session.get("access_token")
    if not raw_token:
        return False
    try:
        payload = jwt.decode(raw_token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return False
    return bool(payload.get("sub"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html")


@router.get("/", response_class=HTMLResponse, response_model=None)
async def dashboard(request: Request) -> Response:
    if not _has_session_access_token(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/lists/{list_id}", response_class=HTMLResponse, response_model=None)
async def list_detail(request: Request, list_id: str) -> Response:
    if not _has_session_access_token(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "list_detail.html", {"list_id": list_id})


@router.get("/preview", response_class=HTMLResponse)
async def preview_dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    if not settings.preview_mode:
        raise HTTPException(status_code=404)

    context = await fetch_preview_context(db)
    if context is None:
        raise HTTPException(status_code=503, detail="Preview data has not been seeded")

    return templates.TemplateResponse(request, "preview.html", context)
