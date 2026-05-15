from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_serializer

from app.schemas.common import ORMModel


class PasskeyRegisterStartRequest(BaseModel):
    email: EmailStr
    display_name: str


class PasskeyLoginStartRequest(BaseModel):
    email: EmailStr | None = None


class PasskeyNameRequest(BaseModel):
    name: str = Field(min_length=1)


class PasskeyFinishRequest(BaseModel):
    credential: dict[str, Any]


class PasskeyAddLinkStartRequest(BaseModel):
    token: str = Field(min_length=1)


class PasskeyAddLinkFinishRequest(PasskeyAddLinkStartRequest):
    credential: dict[str, Any]


class PasskeyOut(ORMModel):
    id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None

    @field_serializer("created_at", "last_used_at")
    def serialize_utc_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.isoformat().replace("+00:00", "Z")


class PasswordAuthRequest(BaseModel):
    email: EmailStr
    passkey: str = Field(min_length=8)


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    display_name: str
    is_admin: bool
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UITestBootstrapRequest(BaseModel):
    email: EmailStr


class UITestBootstrapOut(BaseModel):
    access_token: str
    display_name: str
    user_id: UUID
