"""Attendance routes."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import DbSession, get_current_user, require_roles
from app.models import User, UserRole
from app.schemas import AttendanceResponse, AttendanceSummaryResponse
from app.services import attendance as attendance_service
from app.services.attendance import (
    AlreadyCheckedInError,
    AlreadyCheckedOutError,
    AttendanceNotFoundError,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])

AdminOrHr = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.HR)),
]


def _linked_employee_id(current_user: User) -> int:
    if current_user.employee_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No linked employee record",
        )
    return current_user.employee_id


@router.post(
    "/check-in",
    response_model=AttendanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def check_in(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> AttendanceResponse:
    """Create today's attendance row for the current user."""
    employee_id = _linked_employee_id(current_user)
    try:
        attendance = attendance_service.check_in(db, employee_id)
    except AlreadyCheckedInError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already checked in today",
        ) from None

    return AttendanceResponse.model_validate(attendance)


@router.post("/check-out", response_model=AttendanceResponse)
def check_out(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> AttendanceResponse:
    """Set the check-out time on today's attendance row."""
    employee_id = _linked_employee_id(current_user)
    try:
        attendance = attendance_service.check_out(db, employee_id)
    except AttendanceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No check-in found for today",
        ) from None
    except AlreadyCheckedOutError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already checked out today",
        ) from None

    return AttendanceResponse.model_validate(attendance)


@router.get("/me", response_model=list[AttendanceResponse])
def my_attendance(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[AttendanceResponse]:
    """Return the current user's last 30 days, newest first."""
    employee_id = _linked_employee_id(current_user)
    rows = attendance_service.list_my_attendance(db, employee_id, days=30)
    return [AttendanceResponse.model_validate(row) for row in rows]


@router.get("/summary", response_model=AttendanceSummaryResponse)
def summary(
    _current_user: AdminOrHr,
    attendance_date: date | None = Query(default=None, alias="date"),
) -> AttendanceSummaryResponse:
    """Return attendance totals for a date. Admin/hr only."""
    target_date = attendance_date or date.today()
    data = attendance_service.attendance_summary(target_date)
    return AttendanceSummaryResponse.model_validate(data)
