"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.deps import DbSession, get_current_user, require_roles
from app.models import User, UserRole
from app.schemas import RegisterRequest, TokenResponse, UserResponse
from app.security import create_access_token, verify_password
from app.services.employees import (
    DuplicateEmailError,
    create_employee_with_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> TokenResponse:
    """Exchange email and password for a bearer token."""
    email = form_data.username.strip().lower()
    user = db.scalar(select(User).where(User.email == email))

    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value)
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    db: DbSession,
    _admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> UserResponse:
    """Create an employee and linked user. Admin only."""
    try:
        _employee, user = create_employee_with_user(
            db,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            department=payload.department,
            designation=payload.designation,
            role=payload.role,
        )
    except DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from None

    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the authenticated user."""
    return UserResponse.model_validate(current_user)
