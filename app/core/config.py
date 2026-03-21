from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Listerine"
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = "sqlite+aiosqlite:///./listerine.db"
    secure_cookies: bool = False
    webauthn_rp_id: str | None = None
    seed_data_path: str | None = None
    preview_mode: bool = False
    preview_seed_data: bool = False
    preview_ui_e2e_seed_data: bool = False
    bootstrap_admin_email: EmailStr | None = None


settings = Settings()
