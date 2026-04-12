from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from auth.exceptions import AuthError
from config.settings import settings
from db import user_store

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    # bcrypt uses at most 72 bytes; truncate so passlib/bcrypt never raises.
    password = password[:72]
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    password = password[:72]
    return _pwd_context.verify(password, hashed)


def _jwt_secret() -> str:
    return (settings.jwt_secret_key or "").strip()


def create_access_token(*, user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=max(1, int(settings.jwt_expire_minutes)))
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError:
        raise AuthError(401, "Invalid or expired Bearer token") from None


def _parse_bearer_token_from_authorization_header(auth_header: str) -> Optional[str]:
    """Extract token from ``Authorization`` value; supports ``Bearer <token>`` with flexible spacing."""
    if not auth_header or not str(auth_header).strip():
        return None
    parts = str(auth_header).strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _extract_bearer_token(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    if creds is not None:
        scheme = (creds.scheme or "").lower()
        token = (creds.credentials or "").strip()
        if scheme == "bearer" and token:
            return token
    raw = request.headers.get("Authorization") or request.headers.get("authorization")
    return _parse_bearer_token_from_authorization_header(raw or "")


def _user_from_access_token(token: str) -> dict:
    payload = decode_access_token(token)
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise AuthError(401, "Invalid or expired Bearer token") from None

    user = user_store.get_user_by_id(user_id)
    if user is None:
        raise AuthError(401, "User no longer exists; sign in again") from None
    return user


def resolve_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials],
    *,
    body_email: Optional[str] = None,
) -> dict:
    """
    Resolve the authenticated user from ``Authorization: Bearer <token>`` when present.
    If ``settings.auth_dev_fallback_email`` is enabled and no usable Bearer token is sent,
    fall back to ``?email=``, ``X-Dev-User-Email`` header, or ``body_email`` (JSON field).
    """
    token = _extract_bearer_token(request, creds)
    if token:
        return _user_from_access_token(token)

    if settings.auth_dev_fallback_email:
        q_email = (request.query_params.get("email") or "").strip()
        h_email = (
            request.headers.get("X-Dev-User-Email")
            or request.headers.get("x-dev-user-email")
            or ""
        ).strip()
        b_email = (body_email or "").strip()
        email = q_email or h_email or b_email
        if email:
            user = user_store.get_user_by_email(email)
            if user is None:
                raise AuthError(
                    401,
                    f"No registered user for email {email!r} (dev fallback)",
                ) from None
            return user

    raise AuthError(
        401,
        "Authorization missing or invalid. Send header: Authorization: Bearer <access_token>",
    )


def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    return resolve_current_user(request, creds, body_email=None)


def get_current_user_payload(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Dict[str, Any]:
    token = _extract_bearer_token(request, creds)
    if not token:
        raise AuthError(
            401,
            "Authorization missing or invalid. Send header: Authorization: Bearer <access_token>",
        )
    return decode_access_token(token)
