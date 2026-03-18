from fastapi import FastAPI, Request
from markupsafe import Markup
from fastapi.responses import RedirectResponse
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend

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
    column_list = [Category.name, Category.color]
    form_columns = [Category.name, Category.color]
    form_widget_args = {"color": {"type": "color"}}
    column_formatters = {
        Category.color: lambda model, attr: (
            Markup(
                f'<span style="display:inline-block;width:0.9rem;height:0.9rem;'
                f"border-radius:999px;background:{model.color};margin-right:0.45rem;"
                f'vertical-align:middle;"></span>{model.color}'
            )
            if model.color
            else ""
        )
    }


def configure_admin(app: FastAPI) -> Admin:
    admin = Admin(
        app=app,
        engine=engine,
        title="Listerine Admin",
        authentication_backend=SessionAdminAuth(),
    )
    admin.add_view(UserAdmin)
    admin.add_view(CategoryAdmin)
    return admin
