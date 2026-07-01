"""Authentication routes — JWT login + current-user."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    Role,
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.models import User
from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.api import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserInfo,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
def register(
    payload: RegisterRequest, db: Session = Depends(get_db)
) -> TokenResponse:
    """Self-service sign up. New accounts get the read-only Viewer role and are
    signed in immediately (a token is returned)."""
    username = payload.username.strip()
    if len(username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be at least 3 characters.",
        )
    if len(payload.password) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 4 characters.",
        )
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That username is already taken.",
        )
    role = Role.VIEWER
    user = User(
        username=username,
        hashed_password=hash_password(payload.password),
        role=role.value,
    )
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.username, role=role)
    return TokenResponse(access_token=token, role=role.value)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    try:
        role = Role(user.role)
    except ValueError:
        role = Role.VIEWER
    token = create_access_token(subject=user.username, role=role)
    return TokenResponse(access_token=token, role=role.value)


@router.get("/me", response_model=UserInfo)
def me(user: User = Depends(get_current_user)) -> UserInfo:
    return UserInfo(username=user.username, role=user.role)
