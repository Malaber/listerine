from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class PasskeyRegisterStartRequest(BaseModel):
    email: EmailStr
    display_name: str


class PasskeyLoginStartRequest(BaseModel):
    email: EmailStr


class PasskeyFinishRequest(BaseModel):
    credential: dict[str, Any]


class PasswordAuthRequest(BaseModel):
    email: EmailStr
    passkey: str = Field(min_length=8)


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    display_name: str
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
