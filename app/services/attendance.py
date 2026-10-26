"""Attendance business logic and database access."""

from datetime import date as Date
from datetime import datetime, time, timedelta
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Attendance, AttendanceStatus, Employee


class AlreadyCheckedInError(Exception):
    """Raised when today's attendance row already exists."""


class AttendanceNotFoundError(Exception):
    """Raised when today's attendance row or check-in is missing."""


class AlreadyCheckedOutError(Exception):
    """Raised when today's attendance row already has a check-out."""


class DepartmentAttendanceSummary(TypedDict):
    department: str
    present: int
    total: int


class AttendanceSummary(TypedDict):
    date: Date
    present: int
    late: int
    absent: int
    by_department: list[DepartmentAttendanceSummary]


def check_in(db: Session, employee_id: int) -> Attendance:
    """Create today's attendance row with a local-time check-in."""
    now = datetime.now()
    today = now.date()

    existing = db.scalar(
        select(Attendance).where(
            Attendance.employee_id == employee_id,
            Attendance.date == today,
        )
    )
    if existing is not None:
        raise AlreadyCheckedInError

    status = (
        AttendanceStatus.PRESENT
        if now.time() < time(10, 0)
        else AttendanceStatus.LATE
    )
    attendance = Attendance(
        employee_id=employee_id,
        date=today,
        check_in=now,
        check_out=None,
        status=status,
    )
    db.add(attendance)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AlreadyCheckedInError from None

    db.refresh(attendance)
    return attendance


def check_out(db: Session, employee_id: int) -> Attendance:
    """Set the check-out time on today's attendance row."""
    now = datetime.now()
    today = now.date()

    attendance = db.scalar(
        select(Attendance).where(
            Attendance.employee_id == employee_id,
            Attendance.date == today,
        )
    )
    if attendance is None or attendance.check_in is None:
        raise AttendanceNotFoundError
    if attendance.check_out is not None:
        raise AlreadyCheckedOutError

    attendance.check_out = now
    db.commit()
    db.refresh(attendance)
    return attendance


def list_my_attendance(
    db: Session,
    employee_id: int,
    days: int = 30,
) -> list[Attendance]:
    """Return attendance from the last ``days`` calendar days, newest first."""
    today = Date.today()
    start = today - timedelta(days=days - 1)
    statement = (
        select(Attendance)
        .where(
            Attendance.employee_id == employee_id,
            Attendance.date >= start,
            Attendance.date <= today,
        )
        .order_by(Attendance.date.desc(), Attendance.id.desc())
    )
    return list(db.scalars(statement))


def get_my_attendance_today(
    db: Session,
    employee_id: int,
) -> Attendance | None:
    """Return today's attendance row, or None when absent."""
    rows = list_my_attendance(db, employee_id, days=1)
    return rows[0] if rows else None


def attendance_summary(date: Date) -> AttendanceSummary:
    """Summarize attendance for a date using server-local calendar dates.

    Read-only and self-contained so the AI layer can call it as a tool.
    """
    with SessionLocal() as db:
        present = (
            db.scalar(
                select(func.count())
                .select_from(Attendance)
                .where(
                    Attendance.date == date,
                    Attendance.status == AttendanceStatus.PRESENT,
                )
            )
            or 0
        )
        late = (
            db.scalar(
                select(func.count())
                .select_from(Attendance)
                .where(
                    Attendance.date == date,
                    Attendance.status == AttendanceStatus.LATE,
                )
            )
            or 0
        )
        total_employees = db.scalar(select(func.count()).select_from(Employee)) or 0
        absent = max(total_employees - present - late, 0)

        department_totals = db.execute(
            select(Employee.department, func.count(Employee.id))
            .group_by(Employee.department)
            .order_by(Employee.department)
        ).all()
        present_by_department = dict(
            db.execute(
                select(Employee.department, func.count(Attendance.id))
                .select_from(Employee)
                .join(Attendance, Attendance.employee_id == Employee.id)
                .where(
                    Attendance.date == date,
                    Attendance.status == AttendanceStatus.PRESENT,
                )
                .group_by(Employee.department)
            ).all()
        )

        by_department: list[DepartmentAttendanceSummary] = [
            {
                "department": department,
                "present": present_by_department.get(department, 0),
                "total": total,
            }
            for department, total in department_totals
        ]

        return {
            "date": date,
            "present": present,
            "late": late,
            "absent": absent,
            "by_department": by_department,
        }
