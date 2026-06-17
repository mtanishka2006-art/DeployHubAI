"""Shared API dependencies: current-user resolution and RBAC guards."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import Role, TokenData, decode_access_token, role_satisfies
from app.db.models import User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/login", auto_error=True
)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    data: TokenData | None = decode_access_token(token)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.username == data.username).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found/inactive"
        )
    return user


def require_role(minimum: Role):
    """Dependency factory enforcing a minimum role (RBAC hierarchy)."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        try:
            actual = Role(user.role)
        except ValueError:
            actual = Role.VIEWER
        if not role_satisfies(actual, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{minimum.value}' or higher",
            )
        return user

    return _guard
