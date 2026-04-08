import json
from collections.abc import Iterable

from pydantic import EmailStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError
from pydantic_settings.sources import EnvSettingsSource


class ConfigurationError(RuntimeError):
    """Raised when application settings cannot be loaded cleanly."""


def _format_invalid_env_value(value: object, *, limit: int = 160) -> str:
    rendered = repr(value)
    if len(rendered) <= limit:
        return rendered
    return f"{rendered[: limit - 3]}..."


def _join_validation_path(parts: Iterable[object]) -> str:
    return ".".join(str(part) for part in parts) or "<settings>"


class FriendlyEnvSettingsSource(EnvSettingsSource):
    def prepare_field_value(self, field_name, field, value, value_is_complex):
        try:
            return super().prepare_field_value(field_name, field, value, value_is_complex)
        except json.JSONDecodeError as exc:
            env_name = self._extract_field_info(field, field_name)[0][1]
            raise ValueError(
                f'Invalid JSON in environment variable "{env_name}" for settings field '
                f'"{field_name}". Expected JSON compatible with {field.annotation!r}. '
                f"Received {_format_invalid_env_value(value)}."
            ) from exc


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Listerine"
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 28
    session_max_age_seconds: int = 60 * 60 * 24 * 180
    session_idle_timeout_seconds: int = 60 * 60 * 24 * 28
    auth_flow_expire_seconds: int = 10 * 60
    database_url: str = "sqlite+aiosqlite:///./listerine.db"
    secure_cookies: bool = False
    webauthn_rp_id: str | None = None
    seed_data_path: str | None = None
    bootstrap_admin_email: EmailStr | None = None

    @field_validator("bootstrap_admin_email", mode="before")
    @classmethod
    def normalize_blank_bootstrap_admin_email(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            FriendlyEnvSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


def load_settings(settings_class: type[BaseSettings]) -> BaseSettings:
    try:
        return settings_class()
    except ValidationError as exc:
        details = "; ".join(
            f"{_join_validation_path(error['loc'])}: {error['msg']}" for error in exc.errors()
        )
        raise ConfigurationError(f"Invalid application configuration. {details}") from None
    except SettingsError as exc:
        detail = str(exc.__cause__ or exc)
        raise ConfigurationError(f"Invalid application configuration. {detail}") from None


def build_settings() -> Settings:
    return load_settings(Settings)


settings = build_settings()
