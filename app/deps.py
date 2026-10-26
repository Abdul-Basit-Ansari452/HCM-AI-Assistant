"""Shared FastAPI dependencies.

Role checks are implemented here as dependencies so route handlers stay free
of authorization logic.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import User, UserRole
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    """Resolve the bearer token to an active user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise credentials_exception

    try:
        user_id = int(subject)
    except ValueError:
        raise credentials_exception from None

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception

    role_claim = payload.get("role")
    if not isinstance(role_claim, str) or role_claim != user.role.value:
        raise credentials_exception

    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    """Build a dependency that allows only the given roles."""
    allowed = frozenset(roles)

    def dependency(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency
