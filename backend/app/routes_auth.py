from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    get_current_user,
    get_session,
    hash_password,
    verify_password,
)
from app.config import load_settings
from app.models import User
from app.schemas import Credentials, RegistrationResponse, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


def normalized_email(email: str) -> str:
    return email.strip().lower()


def token_response(user: User) -> TokenResponse:
    settings = load_settings()
    return TokenResponse(
        access_token=create_access_token(user.id, settings=settings),
        expires_in=settings.access_token_minutes * 60,
    )


@router.post(
    "/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED
)
def register(credentials: Credentials, session: Session = Depends(get_session)):
    email = normalized_email(str(credentials.email))
    user = User(email=email, password_hash=hash_password(credentials.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from None
    session.refresh(user)
    return RegistrationResponse(user=user, token=token_response(user))


@router.post("/login", response_model=TokenResponse)
def login(credentials: Credentials, session: Session = Depends(get_session)):
    user = session.scalar(
        select(User).where(User.email == normalized_email(str(credentials.email)))
    )
    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_response(user)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user
