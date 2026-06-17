"""Authentication, JWT handling and role-based access control (RBAC)."""
from __future__ import annotations

import enum
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# bcrypt hard-limits passwords to 72 bytes; we truncate defensively rather than
# error. Using bcrypt directly avoids the brittle passlib<->bcrypt version
# coupling.
_BCRYPT_MAX_BYTES = 72


class Role(str, enum.Enum):
    """Platform roles, ordered from most to least privileged."""

    ADMIN = "Admin"
    SRE = "SRE"
    DEVOPS = "DevOps Engineer"
    VIEWER = "Viewer"


# Privilege hierarchy: a role inherits every permission of roles below it.
_ROLE_RANK = {
    Role.VIEWER: 0,
    Role.DEVOPS: 1,
    Role.SRE: 2,
    Role.ADMIN: 3,
}


def role_satisfies(actual: Role, required: Role) -> bool:
    """True if `actual` is at least as privileged as `required`."""
    return _ROLE_RANK[actual] >= _ROLE_RANK[required]


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_encode(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str, role: Role, expires_minutes: Optional[int] = None
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "role": role.value,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


class TokenData:
    def __init__(self, username: str, role: Role):
        self.username = username
        self.role = role


def decode_access_token(token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        username = payload.get("sub")
        role_value = payload.get("role")
        if username is None or role_value is None:
            return None
        return TokenData(username=username, role=Role(role_value))
    except (JWTError, ValueError):
        return None


def roles_at_least(required: Role) -> List[Role]:
    """All roles that satisfy a minimum required role (for documentation)."""
    return [r for r in Role if role_satisfies(r, required)]
