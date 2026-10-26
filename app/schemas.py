"""Pydantic v2 schemas shared across routes."""

from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models import AttendanceStatus, UserRole


def _validate_bcrypt_password(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes")
    return value


BcryptPassword = Annotated[
    str,
    Field(min_length=8, max_length=72),
    AfterValidator(_validate_bcrypt_password),
]


class HealthResponse(BaseModel):
    """Response for the healthcheck endpoint."""

    status: str


class ORMModel(BaseModel):
    """Base schema for responses built from SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """OAuth2 bearer token response."""

    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """Payload for admin-created users."""

    email: str = Field(min_length=3, max_length=255)
    password: BcryptPassword
    full_name: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=80)
    designation: str = Field(min_length=1, max_length=120)
    role: UserRole


class UserResponse(ORMModel):
    """Safe public representation of a user."""

    id: int
    email: str
    role: UserRole
    employee_id: int | None


class EmployeeCreate(BaseModel):
    """Payload for creating an employee and linked user."""

    email: str = Field(min_length=3, max_length=255)
    password: BcryptPassword
    full_name: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=80)
    designation: str = Field(min_length=1, max_length=120)


class EmployeeUpdate(BaseModel):
    """Mutable employee profile fields."""

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, min_length=1, max_length=80)
    designation: str | None = Field(default=None, min_length=1, max_length=120)


class EmployeeResponse(ORMModel):
    """Safe public representation of an employee."""

    id: int
    full_name: str
    email: str
    department: str
    designation: str
    join_date: date


class AttendanceResponse(ORMModel):
    """One attendance row."""

    id: int
    employee_id: int
    date: date
    check_in: datetime | None
    check_out: datetime | None
    status: AttendanceStatus


class DepartmentAttendanceResponse(BaseModel):
    """Present count for one department."""

    department: str
    present: int
    total: int


class AttendanceSummaryResponse(BaseModel):
    """Daily attendance summary."""

    date: date
    present: int
    late: int
    absent: int
    by_department: list[DepartmentAttendanceResponse]
