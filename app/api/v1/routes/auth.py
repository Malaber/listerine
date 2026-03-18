import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import (
    PasskeyFinishRequest,
    PasskeyLoginStartRequest,
    PasskeyRegisterStartRequest,
    PasswordAuthRequest,
    TokenOut,
    UserOut,
)
from app.services.preview import PREVIEW_EMAIL

router = APIRouter(prefix="/auth", tags=["auth"])

_REGISTER_SESSION_KEY = "passkey_register"
_LOGIN_SESSION_KEY = "passkey_login"


def _rp_id_for_request(request: Request) -> str:
    host = request.url.hostname
    if host is None:
        raise HTTPException(
            status_code=400,
            detail="Request host is required for passkeys",
        )
    return host


def _origin_for_request(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _password_auth_disabled() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail="Password-based auth is disabled. Use the passkey registration and login endpoints.",
    )


async def _apply_bootstrap_admin_email(db: AsyncSession, user: User) -> User:
    if settings.bootstrap_admin_email is None:
        return user

    if user.email.casefold() != str(settings.bootstrap_admin_email).casefold():
        return user

    if user.is_admin:
        return user

    user.is_admin = True
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/register/options")
async def begin_passkey_registration(
    payload: PasskeyRegisterStartRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Email already exists")

    user_id = uuid4()
    options = generate_registration_options(
        rp_id=_rp_id_for_request(request),
        rp_name=settings.app_name,
        user_name=payload.email,
        user_id=user_id.bytes,
        user_display_name=payload.display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    request.session[_REGISTER_SESSION_KEY] = {
        "challenge": bytes_to_base64url(options.challenge),
        "email": payload.email,
        "display_name": payload.display_name,
        "origin": _origin_for_request(request),
        "rp_id": _rp_id_for_request(request),
        "user_id": str(user_id),
    }
    return json.loads(options_to_json(options))


@router.post("/register/verify", response_model=UserOut)
async def finish_passkey_registration(
    payload: PasskeyFinishRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    pending = request.session.get(_REGISTER_SESSION_KEY)
    if pending is None:
        raise HTTPException(status_code=400, detail="Registration session expired")

    existing = await db.execute(select(User).where(User.email == pending["email"]))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Email already exists")

    try:
        verified = verify_registration_response(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=pending["rp_id"],
            expected_origin=pending["origin"],
            require_user_verification=True,
        )
    except Exception as exc:  # pragma: no cover - exercised via API tests with monkeypatch
        raise HTTPException(status_code=400, detail="Passkey registration failed") from exc

    user = User(
        id=UUID(pending["user_id"]),
        email=pending["email"],
        password_hash="",
        passkey_credential_id=bytes_to_base64url(verified.credential_id),
        passkey_public_key=verified.credential_public_key,
        passkey_sign_count=verified.sign_count,
        display_name=pending["display_name"],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user = await _apply_bootstrap_admin_email(db, user)

    request.session.pop(_REGISTER_SESSION_KEY, None)
    request.session["access_token"] = create_access_token(user.id)
    return user


@router.post("/login/options")
async def begin_passkey_login(
    payload: PasskeyLoginStartRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or user.passkey_credential_id is None:
        raise HTTPException(status_code=404, detail="No passkey found for that email")

    options = generate_authentication_options(
        rp_id=_rp_id_for_request(request),
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(user.passkey_credential_id))
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    request.session[_LOGIN_SESSION_KEY] = {
        "challenge": bytes_to_base64url(options.challenge),
        "origin": _origin_for_request(request),
        "rp_id": _rp_id_for_request(request),
        "user_id": str(user.id),
    }
    return json.loads(options_to_json(options))


@router.post("/login/verify", response_model=TokenOut)
async def finish_passkey_login(
    payload: PasskeyFinishRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenOut:
    pending = request.session.get(_LOGIN_SESSION_KEY)
    if pending is None:
        raise HTTPException(status_code=400, detail="Login session expired")

    result = await db.execute(select(User).where(User.id == UUID(pending["user_id"])))
    user = result.scalar_one_or_none()
    if user is None or user.passkey_public_key is None:
        raise HTTPException(status_code=404, detail="No passkey found for that user")

    try:
        verified = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=pending["rp_id"],
            expected_origin=pending["origin"],
            credential_public_key=user.passkey_public_key,
            credential_current_sign_count=user.passkey_sign_count,
            require_user_verification=True,
        )
    except Exception as exc:  # pragma: no cover - exercised via API tests with monkeypatch
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid passkey",
        ) from exc

    user.passkey_sign_count = verified.new_sign_count
    await db.commit()
    await db.refresh(user)
    user = await _apply_bootstrap_admin_email(db, user)

    request.session.pop(_LOGIN_SESSION_KEY, None)
    token = create_access_token(user.id)
    request.session["access_token"] = token
    return TokenOut(access_token=token)


@router.post("/register", response_model=None)
async def register_password_disabled(_: PasswordAuthRequest) -> None:
    raise _password_auth_disabled()


@router.post("/login", response_model=None)
async def login_password_disabled(_: PasswordAuthRequest) -> None:
    raise _password_auth_disabled()


@router.post("/preview/login", response_model=TokenOut)
async def preview_login(request: Request, db: AsyncSession = Depends(get_db)) -> TokenOut:
    if not settings.preview_mode:
        raise HTTPException(status_code=404)

    result = await db.execute(select(User).where(User.email == PREVIEW_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=503, detail="Preview data has not been seeded")

    token = create_access_token(user.id)
    request.session["access_token"] = token
    return TokenOut(access_token=token)


@router.post("/logout")
async def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"message": "logged out"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
