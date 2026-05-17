import asyncio
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from markupsafe import Markup
from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.authentication import login_required
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models import Category, PasskeyAddLink, User
from app.services.backups import BackupError, BackupResult, create_database_backup
from app.services.passkey_reset import build_passkey_add_link, issue_passkey_reset
from app.web.routes import _get_session_user


PASSKEY_ADD_LINK_DEFAULT_HOURS = 24
PASSKEY_ADD_LINK_MIN_HOURS = 1
PASSKEY_ADD_LINK_MAX_HOURS = 720


def _passkey_add_link_duration_hours(raw_value: object) -> int:
    try:
        duration_hours = int(str(raw_value or PASSKEY_ADD_LINK_DEFAULT_HOURS))
    except ValueError as exc:
        raise ValueError("Passkey add link duration must be a whole number of hours.") from exc
    if duration_hours < PASSKEY_ADD_LINK_MIN_HOURS or duration_hours > PASSKEY_ADD_LINK_MAX_HOURS:
        raise ValueError(
            f"Passkey add link duration must be between {PASSKEY_ADD_LINK_MIN_HOURS} "
            f"and {PASSKEY_ADD_LINK_MAX_HOURS} hours."
        )
    return duration_hours


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
    column_sortable_list = column_list
    form_columns = [User.email, User.display_name, User.is_admin, User.is_active]
    page_size = 50
    page_size_options = [50, 100, 200]
    can_create = False
    edit_template = "planini_admin/user_edit.html"

    def form_edit_query(self, request: Request):
        return super().form_edit_query(request).options(selectinload(User.passkey_add_links))

    async def _render_edit(
        self,
        request: Request,
        user: User,
        *,
        passkey_add: dict[str, object] | None = None,
        passkey_add_error: str | None = None,
        passkey_add_notice: str | None = None,
    ) -> Response:
        form_class = await self.scaffold_form(self._form_edit_rules)
        return await self.templates.TemplateResponse(
            request,
            self.edit_template,
            {
                "obj": user,
                "model_view": self,
                "form": form_class(obj=user),
                "passkey_add": passkey_add,
                "passkey_add_error": passkey_add_error,
                "passkey_add_notice": passkey_add_notice,
            },
        )

    async def _load_user_with_add_links(self, user_id: UUID) -> User | None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).options(selectinload(User.passkey_add_links)).where(User.id == user_id)
            )
            return result.scalar_one_or_none()

    @expose("/{pk}/passkey-add-link", methods=["POST"], include_in_schema=False)
    async def generate_passkey_add_link(self, request: Request) -> Response:
        user_id = UUID(request.path_params["pk"])
        edit_url = request.url_for("admin:edit", identity=self.identity, pk=str(user_id))
        form = await request.form()
        try:
            duration_hours = _passkey_add_link_duration_hours(form.get("valid_for_hours"))
        except ValueError as exc:
            return RedirectResponse(
                url=str(
                    edit_url.include_query_params(
                        passkey_add_error=str(exc),
                        passkey_add_valid_for_hours=form.get("valid_for_hours") or "",
                    )
                ),
                status_code=303,
            )

        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user is None:
                return RedirectResponse(url="/admin/user/list", status_code=303)

            token, link = await issue_passkey_reset(
                session, user, ttl=timedelta(hours=duration_hours)
            )

        user = await self._load_user_with_add_links(user_id)
        assert user is not None
        reset_link = build_passkey_add_link(str(request.base_url), token, identifier=link.short_id)
        return await self._render_edit(
            request,
            user,
            passkey_add={
                "link": reset_link,
                "email": user.email,
                "identifier": link.short_id,
                "expires_at": link.expires_at.isoformat(),
                "valid_for_hours": str(duration_hours),
            },
        )

    @expose(
        "/{pk}/passkey-add-links/{link_id}/duration",
        methods=["POST"],
        include_in_schema=False,
    )
    async def update_passkey_add_link_duration(self, request: Request) -> Response:
        user_id = UUID(request.path_params["pk"])
        link_id = UUID(request.path_params["link_id"])
        edit_url = request.url_for("admin:edit", identity=self.identity, pk=str(user_id))
        form = await request.form()
        try:
            duration_hours = _passkey_add_link_duration_hours(form.get("valid_for_hours"))
        except ValueError as exc:
            return RedirectResponse(
                url=str(edit_url.include_query_params(passkey_add_error=str(exc))),
                status_code=303,
            )

        async with AsyncSessionLocal() as session:
            link = await session.get(PasskeyAddLink, link_id)
            if link is None or link.user_id != user_id:
                return RedirectResponse(url=str(edit_url), status_code=303)
            if link.used_at is not None:
                return RedirectResponse(
                    url=str(
                        edit_url.include_query_params(
                            passkey_add_error="Used passkey add links cannot be extended."
                        )
                    ),
                    status_code=303,
                )

            link.expires_at = datetime.now(UTC) + timedelta(hours=duration_hours)
            await session.commit()

        return RedirectResponse(
            url=str(
                edit_url.include_query_params(
                    passkey_add_notice=(
                        f"Passkey add link {str(link_id).split('-', maxsplit=1)[0]} "
                        f"duration updated to {duration_hours} hours."
                    )
                )
            ),
            status_code=303,
        )


class CategoryAdmin(ModelView, model=Category):
    name = "Category"
    name_plural = "Categories"
    icon = "fa-solid fa-tag"
    column_list = [Category.name, Category.color, Category.aliases_text]
    column_sortable_list = column_list
    form_columns = [Category.name, Category.color, Category.aliases_text]
    column_labels = {Category.aliases_text: "Aliases"}
    page_size = 50
    page_size_options = [50, 100, 200]
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


class BackupAdmin(BaseView):
    name = "Backups"
    icon = "fa-solid fa-database"

    @expose("/backups", methods=["GET", "POST"], identity="backups", include_in_schema=False)
    async def backups(self, request: Request) -> Response:
        result: BackupResult | None = None
        error: str | None = None
        if request.method == "POST":
            try:
                result = await asyncio.to_thread(create_database_backup)
            except BackupError as exc:
                error = str(exc)

        return await self.templates.TemplateResponse(
            request,
            "planini_admin/backups.html",
            {
                "backup_directory": settings.backup_directory,
                "backup_result": result,
                "backup_error": error,
            },
        )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PROJECT_ROOT / "VERSION"


@lru_cache(maxsize=1)
def get_application_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "development"


class PlaniniAdmin(Admin):
    @login_required
    async def index(self, request: Request) -> Response:
        return await self.templates.TemplateResponse(
            request,
            "planini_admin/index.html",
            {"planini_version": get_application_version()},
        )


def configure_admin(app: FastAPI) -> Admin:
    admin = PlaniniAdmin(
        app=app,
        engine=engine,
        title="Planini Admin",
        templates_dir=str(PROJECT_ROOT / "app" / "admin_templates"),
        authentication_backend=SessionAdminAuth(),
    )
    admin.add_view(UserAdmin)
    admin.add_view(CategoryAdmin)
    admin.add_base_view(BackupAdmin)
    return admin
