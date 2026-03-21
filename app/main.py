from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.admin import configure_admin
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import run_migrations
from app.services.fixture_seed import ensure_seed_data
from app.services.preview import ensure_preview_seed_data, ensure_ui_e2e_seed_data
from app.web.routes import router as web_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_migrations()
    if settings.seed_data_path or settings.preview_seed_data:
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            if settings.seed_data_path:
                await ensure_seed_data(session, settings.seed_data_path)
            if settings.preview_seed_data:
                await ensure_preview_seed_data(session)
                if settings.preview_ui_e2e_seed_data:
                    await ensure_ui_e2e_seed_data(session)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware, secret_key=settings.secret_key, https_only=settings.secure_cookies
)
app.include_router(api_router, prefix="/api/v1")
app.include_router(web_router)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
configure_admin(app)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/api")
async def api_root() -> JSONResponse:
    return JSONResponse({"name": settings.app_name, "version": "v1", "base": "/api/v1"})
