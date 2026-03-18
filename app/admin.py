from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from markupsafe import Markup
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqladmin.authentication import login_required

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models import Category, User
from app.web.routes import _get_session_user


class SessionAdminAuth(AuthenticationBackend):
    def __init__(self) -> None:
        super().__init__(secret_key=settings.secret_key)

    async def login(self, request: Request) -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=303)

    async def logout(self, request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)

    async def authenticate(self, request: Request) -> RedirectResponse | bool:
        async with AsyncSessionLocal() as session:
            user = await _get_session_user(request, session)

        if user is None:
            return RedirectResponse(url="/login", status_code=303)
        if not user.is_admin:
            return RedirectResponse(url="/", status_code=303)
        return True


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    column_list = [User.email, User.display_name, User.is_admin, User.is_active, User.created_at]
    form_columns = [User.email, User.display_name, User.is_admin, User.is_active]
    can_create = False


class CategoryAdmin(ModelView, model=Category):
    name = "Category"
    name_plural = "Categories"
    icon = "fa-solid fa-tag"
    column_list = [Category.name, Category.color, Category.aliases_text]
    form_columns = [Category.name, Category.color, Category.aliases_text]
    column_labels = {Category.aliases_text: "Aliases"}
    form_widget_args = {
        "color": {"type": "color"},
        "aliases_text": {
            "placeholder": "One alias per line, for example:\nBrot\nBroetchen",
            "rows": 4,
        },
    }
    column_formatters = {
        Category.color: lambda model, attr: (
            Markup(
                f'<span style="display:inline-block;width:0.9rem;height:0.9rem;'
                f"border-radius:999px;background:{model.color};margin-right:0.45rem;"
                f'vertical-align:middle;"></span>{model.color}'
            )
            if model.color
            else ""
        ),
        Category.aliases_text: lambda model, attr: ", ".join(model.aliases),
    }


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PROJECT_ROOT / "VERSION"


@lru_cache(maxsize=1)
def get_application_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "unknown"


class ListerineAdmin(Admin):
    @login_required
    async def index(self, request: Request) -> Response:
        return await self.templates.TemplateResponse(
            request,
            "listerine_admin/index.html",
            {"listerine_version": get_application_version()},
        )


def configure_admin(app: FastAPI) -> Admin:
    admin = ListerineAdmin(
        app=app,
        engine=engine,
        title="Listerine Admin",
        templates_dir=str(PROJECT_ROOT / "app" / "admin_templates"),
        authentication_backend=SessionAdminAuth(),
    )
    admin.add_view(UserAdmin)
    admin.add_view(CategoryAdmin)
    return admin
