"""Authentication routes."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import DbSession, get_current_user, require_roles
from app.models import Employee, User, UserRole
from app.schemas import RegisterRequest, TokenResponse, UserResponse
from app.security import create_access_token, hash_password, verify_password

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
    email = payload.email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    employee = Employee(
        full_name=payload.full_name.strip(),
        email=email,
        department=payload.department.strip(),
        designation=payload.designation.strip(),
        join_date=date.today(),
    )
    db.add(employee)

    try:
        db.flush()
        user = User(
            email=email,
            password_hash=hash_password(payload.password),
            role=payload.role,
            employee_id=employee.id,
        )
        db.add(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from None

    db.refresh(user)
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the authenticated user."""
    return UserResponse.model_validate(current_user)
