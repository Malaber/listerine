import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
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
from app.models import Passkey, User
from app.services.auth_sessions import create_auth_session, revoke_auth_session
from app.schemas.auth import (
    PasskeyFinishRequest,
    PasskeyLoginStartRequest,
    PasskeyNameRequest,
    PasskeyOut,
    PasskeyRegisterStartRequest,
    PasswordAuthRequest,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_REGISTER_SESSION_KEY = "passkey_register"
_LOGIN_SESSION_KEY = "passkey_login"
_PASSKEY_ADD_SESSION_KEY = "passkey_add"
_PASSKEY_DELETE_SESSION_KEY = "passkey_delete"
_PASSKEY_RENAME_SESSION_KEY = "passkey_rename"
_DEFAULT_INITIAL_PASSKEY_NAME = "Passkey 1"
_REGISTRATION_FAILURE_DETAIL = (
    "Could not create that account. Try signing in with an existing "
    "passkey or use a different email."
)


def _rp_id_for_request(request: Request) -> str:
    if settings.webauthn_rp_id:
        return settings.webauthn_rp_id
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


def _credential_id_from_payload(payload: PasskeyFinishRequest) -> str:
    credential_id = payload.credential.get("id")
    if not isinstance(credential_id, str) or not credential_id:
        raise HTTPException(status_code=400, detail="Credential id is required")
    return credential_id


def _new_auth_flow_session(**payload: object) -> dict[str, object]:
    return {
        **payload,
        "issued_at": datetime.now(UTC).isoformat(),
    }


def _auth_flow_session_is_valid(pending: dict[str, object] | None) -> bool:
    if pending is None or not isinstance(pending, dict):
        return False

    issued_at_raw = pending.get("issued_at")
    if not isinstance(issued_at_raw, str):
        return False

    try:
        issued_at = datetime.fromisoformat(issued_at_raw)
    except ValueError:
        return False

    if issued_at.tzinfo is None:
        return False

    return datetime.now(UTC) - issued_at < timedelta(seconds=settings.auth_flow_expire_seconds)


async def _load_user_with_passkeys(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(
        select(User).options(selectinload(User.passkeys)).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def _load_user_with_passkeys_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).options(selectinload(User.passkeys)).where(User.email == email)
    )
    return result.scalar_one_or_none()


async def _load_passkey_with_user_by_credential_id(
    db: AsyncSession, credential_id: str
) -> Passkey | None:
    result = await db.execute(
        select(Passkey)
        .options(selectinload(Passkey.user))
        .where(Passkey.credential_id == credential_id)
    )
    return result.scalar_one_or_none()


def _passkey_descriptor(passkey: Passkey) -> PublicKeyCredentialDescriptor:
    return PublicKeyCredentialDescriptor(id=base64url_to_bytes(passkey.credential_id))


def _validated_passkey_name(raw_name: str) -> str:
    name = raw_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Passkey name is required")
    if len(name) > 120:
        raise HTTPException(status_code=400, detail="Passkey name must be 120 characters or fewer")
    return name


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
        **_new_auth_flow_session(
            challenge=bytes_to_base64url(options.challenge),
            email=payload.email,
            display_name=payload.display_name,
            origin=_origin_for_request(request),
            rp_id=_rp_id_for_request(request),
            user_id=str(user_id),
        )
    }
    return json.loads(options_to_json(options))


@router.post("/register/verify", response_model=UserOut)
async def finish_passkey_registration(
    payload: PasskeyFinishRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    pending = request.session.get(_REGISTER_SESSION_KEY)
    if not _auth_flow_session_is_valid(pending):
        request.session.pop(_REGISTER_SESSION_KEY, None)
        raise HTTPException(status_code=400, detail="Registration session expired")

    existing = await _load_user_with_passkeys_by_email(db, pending["email"])
    if existing is not None:
        raise HTTPException(status_code=400, detail=_REGISTRATION_FAILURE_DETAIL)

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

    credential_id = bytes_to_base64url(verified.credential_id)
    if (
        await db.execute(select(Passkey).where(Passkey.credential_id == credential_id))
    ).scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=_REGISTRATION_FAILURE_DETAIL)

    user = User(
        id=UUID(pending["user_id"]),
        email=pending["email"],
        password_hash="",
        display_name=pending["display_name"],
    )
    user.passkeys.append(
        Passkey(
            name=_DEFAULT_INITIAL_PASSKEY_NAME,
            credential_id=credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
        )
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=_REGISTRATION_FAILURE_DETAIL) from exc
    await db.refresh(user)
    user = await _apply_bootstrap_admin_email(db, user)

    await create_auth_session(request, db, user)
    return user


@router.post("/login/options")
async def begin_passkey_login(_: PasskeyLoginStartRequest, request: Request) -> dict:
    options = generate_authentication_options(
        rp_id=_rp_id_for_request(request),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    request.session[_LOGIN_SESSION_KEY] = {
        **_new_auth_flow_session(
            challenge=bytes_to_base64url(options.challenge),
            origin=_origin_for_request(request),
            rp_id=_rp_id_for_request(request),
        )
    }
    return json.loads(options_to_json(options))


@router.post("/login/verify", response_model=TokenOut)
async def finish_passkey_login(
    payload: PasskeyFinishRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenOut:
    pending = request.session.get(_LOGIN_SESSION_KEY)
    if not _auth_flow_session_is_valid(pending):
        request.session.pop(_LOGIN_SESSION_KEY, None)
        raise HTTPException(status_code=400, detail="Login session expired")

    credential_id = _credential_id_from_payload(payload)
    passkey = await _load_passkey_with_user_by_credential_id(db, credential_id)
    if passkey is None:
        raise HTTPException(status_code=404, detail="No passkey found for that credential")
    user = passkey.user
    if user is None:
        raise HTTPException(status_code=404, detail="No user found for that passkey")

    try:
        verified = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=pending["rp_id"],
            expected_origin=pending["origin"],
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:  # pragma: no cover - exercised via API tests with monkeypatch
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid passkey",
        ) from exc

    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(passkey)
    await db.refresh(user)
    user = await _apply_bootstrap_admin_email(db, user)

    token = create_access_token(user.id)
    await create_auth_session(request, db, user)
    return TokenOut(access_token=token)


@router.post("/register", response_model=None)
async def register_password_disabled(_: PasswordAuthRequest) -> None:
    raise _password_auth_disabled()


@router.post("/login", response_model=None)
async def login_password_disabled(_: PasswordAuthRequest) -> None:
    raise _password_auth_disabled()


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await revoke_auth_session(request, db)
    request.session.clear()
    return {"message": "logged out"}


@router.get("/passkeys", response_model=list[PasskeyOut])
async def list_passkeys(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Passkey]:
    refreshed = await _load_user_with_passkeys(db, user.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="User not found")
    return refreshed.passkeys


@router.post("/passkeys/register/options")
async def begin_add_passkey(
    payload: PasskeyNameRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    refreshed = await _load_user_with_passkeys(db, user.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="User not found")
    passkey_name = _validated_passkey_name(payload.name)

    options = generate_registration_options(
        rp_id=_rp_id_for_request(request),
        rp_name=settings.app_name,
        user_name=refreshed.email,
        user_id=refreshed.id.bytes,
        user_display_name=refreshed.display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[_passkey_descriptor(passkey) for passkey in refreshed.passkeys],
    )
    request.session[_PASSKEY_ADD_SESSION_KEY] = {
        **_new_auth_flow_session(
            challenge=bytes_to_base64url(options.challenge),
            origin=_origin_for_request(request),
            rp_id=_rp_id_for_request(request),
            user_id=str(refreshed.id),
            name=passkey_name,
        )
    }
    return json.loads(options_to_json(options))


@router.post("/passkeys/register/verify", response_model=PasskeyOut)
async def finish_add_passkey(
    payload: PasskeyFinishRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Passkey:
    pending = request.session.get(_PASSKEY_ADD_SESSION_KEY)
    if not _auth_flow_session_is_valid(pending):
        request.session.pop(_PASSKEY_ADD_SESSION_KEY, None)
        raise HTTPException(status_code=400, detail="Passkey registration session expired")
    if pending.get("user_id") != str(user.id):
        request.session.pop(_PASSKEY_ADD_SESSION_KEY, None)
        raise HTTPException(status_code=400, detail="Passkey registration session expired")

    try:
        verified = verify_registration_response(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=pending["rp_id"],
            expected_origin=pending["origin"],
            require_user_verification=True,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail="Passkey registration failed") from exc

    credential_id = bytes_to_base64url(verified.credential_id)
    if (
        await db.execute(select(Passkey).where(Passkey.credential_id == credential_id))
    ).scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="That passkey is already registered")

    passkey = Passkey(
        user_id=user.id,
        name=pending["name"],
        credential_id=credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
    )
    db.add(passkey)
    await db.commit()
    await db.refresh(passkey)
    request.session.pop(_PASSKEY_ADD_SESSION_KEY, None)
    return passkey


@router.post("/passkeys/{passkey_id}/rename/options")
async def begin_rename_passkey(
    passkey_id: UUID,
    payload: PasskeyNameRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    refreshed = await _load_user_with_passkeys(db, user.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="User not found")

    target = next((entry for entry in refreshed.passkeys if entry.id == passkey_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Passkey not found")

    options = generate_authentication_options(
        rp_id=_rp_id_for_request(request),
        user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=[_passkey_descriptor(target)],
    )
    request.session[_PASSKEY_RENAME_SESSION_KEY] = {
        **_new_auth_flow_session(
            challenge=bytes_to_base64url(options.challenge),
            origin=_origin_for_request(request),
            rp_id=_rp_id_for_request(request),
            user_id=str(user.id),
            passkey_id=str(passkey_id),
            name=_validated_passkey_name(payload.name),
        )
    }
    return json.loads(options_to_json(options))


@router.post("/passkeys/{passkey_id}/rename/verify", response_model=PasskeyOut)
async def finish_rename_passkey(
    passkey_id: UUID,
    payload: PasskeyFinishRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Passkey:
    pending = request.session.get(_PASSKEY_RENAME_SESSION_KEY)
    if (
        not _auth_flow_session_is_valid(pending)
        or pending.get("user_id") != str(user.id)
        or pending.get("passkey_id") != str(passkey_id)
    ):
        request.session.pop(_PASSKEY_RENAME_SESSION_KEY, None)
        raise HTTPException(status_code=400, detail="Passkey rename session expired")

    refreshed = await _load_user_with_passkeys(db, user.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="User not found")

    target = next((entry for entry in refreshed.passkeys if entry.id == passkey_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Passkey not found")

    credential_id = payload.credential.get("id")
    if credential_id != target.credential_id:
        raise HTTPException(
            status_code=400,
            detail="Confirm the rename with the passkey you are renaming",
        )

    try:
        verified = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=pending["rp_id"],
            expected_origin=pending["origin"],
            credential_public_key=target.public_key,
            credential_current_sign_count=target.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not verify that passkey before renaming",
        ) from exc

    target.name = pending["name"]
    target.sign_count = verified.new_sign_count
    target.last_used_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(target)
    request.session.pop(_PASSKEY_RENAME_SESSION_KEY, None)
    return target


@router.post("/passkeys/{passkey_id}/delete/options")
async def begin_delete_passkey(
    passkey_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    refreshed = await _load_user_with_passkeys(db, user.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="User not found")

    target = next((entry for entry in refreshed.passkeys if entry.id == passkey_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Passkey not found")
    if len(refreshed.passkeys) <= 1:
        raise HTTPException(status_code=400, detail="You cannot delete your last passkey")

    other_passkeys = [entry for entry in refreshed.passkeys if entry.id != passkey_id]
    options = generate_authentication_options(
        rp_id=_rp_id_for_request(request),
        allow_credentials=[_passkey_descriptor(passkey) for passkey in other_passkeys],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    request.session[_PASSKEY_DELETE_SESSION_KEY] = {
        **_new_auth_flow_session(
            challenge=bytes_to_base64url(options.challenge),
            origin=_origin_for_request(request),
            rp_id=_rp_id_for_request(request),
            user_id=str(user.id),
            passkey_id=str(passkey_id),
        )
    }
    return json.loads(options_to_json(options))


@router.post("/passkeys/{passkey_id}/delete/verify")
async def finish_delete_passkey(
    passkey_id: UUID,
    payload: PasskeyFinishRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    pending = request.session.get(_PASSKEY_DELETE_SESSION_KEY)
    if (
        not _auth_flow_session_is_valid(pending)
        or pending.get("user_id") != str(user.id)
        or pending.get("passkey_id") != str(passkey_id)
    ):
        request.session.pop(_PASSKEY_DELETE_SESSION_KEY, None)
        raise HTTPException(status_code=400, detail="Passkey deletion session expired")

    refreshed = await _load_user_with_passkeys(db, user.id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="User not found")

    target = next((entry for entry in refreshed.passkeys if entry.id == passkey_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Passkey not found")
    if len(refreshed.passkeys) <= 1:
        raise HTTPException(status_code=400, detail="You cannot delete your last passkey")

    credential_id = _credential_id_from_payload(payload)
    confirming_passkey = next(
        (
            entry
            for entry in refreshed.passkeys
            if entry.credential_id == credential_id and entry.id != passkey_id
        ),
        None,
    )
    if confirming_passkey is None:
        raise HTTPException(
            status_code=400, detail="Confirm deletion with one of your other passkeys"
        )

    try:
        verified = verify_authentication_response(
            credential=payload.credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=pending["rp_id"],
            expected_origin=pending["origin"],
            credential_public_key=confirming_passkey.public_key,
            credential_current_sign_count=confirming_passkey.sign_count,
            require_user_verification=True,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not verify another passkey before deletion",
        ) from exc

    confirming_passkey.sign_count = verified.new_sign_count
    confirming_passkey.last_used_at = datetime.now(UTC)
    await db.flush()

    await db.execute(delete(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == user.id))
    await db.commit()
    request.session.pop(_PASSKEY_DELETE_SESSION_KEY, None)
    return {"message": "passkey deleted"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
