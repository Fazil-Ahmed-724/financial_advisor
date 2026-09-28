import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import Settings, load_settings
from app.database import SessionLocal
from app.models import User

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def get_session():
    with SessionLocal() as session:
        yield session


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def create_access_token(
    user_id: uuid.UUID,
    *,
    expires_delta: timedelta | None = None,
    settings: Settings | None = None,
) -> str:
    settings = settings or load_settings()
    now = datetime.now(timezone.utc)
    expires = now + (
        expires_delta or timedelta(minutes=settings.access_token_minutes)
    )
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": expires,
        },
        settings.auth_secret,
        algorithm="HS256",
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    try:
        payload = jwt.decode(
            credentials.credentials,
            load_settings().auth_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "type"]},
        )
        if payload["type"] != "access":
            raise unauthorized
        user_id = uuid.UUID(payload["sub"])
    except (InvalidTokenError, ValueError, KeyError):
        raise unauthorized from None

    user = session.get(User, user_id)
    if user is None:
        raise unauthorized
    return user
