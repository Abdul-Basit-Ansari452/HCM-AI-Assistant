"""Pydantic v2 schemas shared across routes."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models import AttendanceStatus, LeaveStatus, LeaveType, UserRole


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


class LeaveCreate(BaseModel):
    """Payload for a self-service leave request."""

    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_date_range(self) -> "LeaveCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class LeaveDraft(BaseModel):
    """AI-extracted leave draft that is never submitted automatically."""

    leave_type: Literal["sick", "casual", "earned"]
    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_date_range(self) -> "LeaveDraft":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class LeaveDraftWarning(BaseModel):
    """A non-blocking issue shown alongside an AI leave draft."""

    code: Literal["insufficient_balance", "overlap", "past_date"]
    message: str
    other_leave_types: list[str] = Field(default_factory=list)
    request_ids: list[int] = Field(default_factory=list)


class LeaveDraftResult(BaseModel):
    """A reviewable leave draft with read-only enrichment."""

    draft: LeaveDraft
    requested_days: int
    remaining_balance: int
    warnings: list[LeaveDraftWarning] = Field(default_factory=list)


class LeaveResponse(ORMModel):
    """Safe public representation of a leave request."""

    id: int
    employee_id: int
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str
    status: LeaveStatus
    created_at: datetime


class PendingLeaveResponse(LeaveResponse):
    """Pending request with employee identity details."""

    employee_name: str
    department: str


class LeaveBalanceResponse(BaseModel):
    """Per-type leave balance with remaining days."""

    leave_type: LeaveType
    total_days: int
    used_days: int
    remaining: int


class DepartmentHeadcountResponse(BaseModel):
    """Employee count for one department."""

    department: str
    count: int


class DashboardSummaryResponse(BaseModel):
    """Admin/hr dashboard summary."""

    total_employees: int
    present_today: int
    late_today: int
    absent_today: int
    on_leave_today: int
    pending_leave_requests: int
    headcount_by_department: list[DepartmentHeadcountResponse]


class MyDashboardResponse(BaseModel):
    """Current employee's dashboard."""

    my_balances: list[LeaveBalanceResponse]
    my_attendance_today: AttendanceResponse | None
    my_pending_requests: list[LeaveResponse]


class AIChatRequest(BaseModel):
    """Payload for the read-only AI assistant."""

    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        """Reject whitespace-only questions."""
        value = value.strip()
        if not value:
            raise ValueError("message must not be empty")
        return value


class AIChatResponse(BaseModel):
    """Answer, tools invoked, and an optional reviewable leave draft."""

    answer: str
    tools_used: list[str] = Field(default_factory=list)
    leave_draft: LeaveDraftResult | None = None


class LeaveParseRequest(BaseModel):
    """Free-text request to turn into a leave draft."""

    transcript: str = Field(min_length=1, max_length=2000)

    @field_validator("transcript")
    @classmethod
    def validate_transcript(cls, value: str) -> str:
        """Reject whitespace-only requests."""
        value = value.strip()
        if not value:
            raise ValueError("transcript must not be empty")
        return value
