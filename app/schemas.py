"""Pydantic v2 schemas shared across routes."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import UserRole


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
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=80)
    designation: str = Field(min_length=1, max_length=120)
    role: UserRole

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return value


class UserResponse(ORMModel):
    """Safe public representation of a user."""

    id: int
    email: str
    role: UserRole
    employee_id: int | None
