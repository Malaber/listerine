from pydantic import EmailStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Listerine"
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 28
    session_max_age_seconds: int = 60 * 60 * 24 * 28
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


settings = Settings()
