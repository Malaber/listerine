from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class RegisterRequest(BaseModel):
    email: EmailStr
    passkey: str = Field(min_length=8)
    display_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    passkey: str


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    display_name: str
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
