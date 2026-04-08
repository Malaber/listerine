from urllib.parse import urlparse

from pydantic import EmailStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    app_base_url: str | None = None
    secure_cookies: bool = False
    webauthn_rp_id: str | None = None
    webcredentials_apps: list[str] = []
    seed_data_path: str | None = None
    bootstrap_admin_email: EmailStr | None = None

    @field_validator("app_base_url", mode="before")
    @classmethod
    def normalize_app_base_url(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().rstrip("/")
        if not normalized:
            return None
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("app_base_url must be a valid http or https URL")
        return normalized

    @field_validator("webcredentials_apps", mode="before")
    @classmethod
    def normalize_webcredentials_apps(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [entry.strip() for entry in value.split(",") if entry.strip()]
        return value

    @field_validator("bootstrap_admin_email", mode="before")
    @classmethod
    def normalize_blank_bootstrap_admin_email(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


settings = Settings()
