"""Seed local development data. Safe to run twice.

Usage: python seed.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models import (
    Attendance,
    AttendanceStatus,
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    Policy,
    User,
    UserRole,
)
from app.security import hash_password

SEED_PASSWORD = "Passw0rd!"


@dataclass(frozen=True, slots=True)
class SeedUser:
    email: str
    full_name: str
    department: str
    designation: str
    role: UserRole
    join_date: date


SEED_USERS: tuple[SeedUser, ...] = (
    SeedUser(
        "admin@x.com",
        "Ayesha Khan",
        "Engineering",
        "Operations Manager",
        UserRole.ADMIN,
        date(2022, 3, 14),
    ),
    SeedUser(
        "hr@x.com",
        "Sara Ahmed",
        "Sales",
        "HR Business Partner",
        UserRole.HR,
        date(2022, 7, 1),
    ),
    SeedUser(
        "employee1@x.com",
        "Omar Ali",
        "Engineering",
        "Software Engineer",
        UserRole.EMPLOYEE,
        date(2023, 2, 20),
    ),
    SeedUser(
        "employee2@x.com",
        "Maya Patel",
        "Engineering",
        "QA Engineer",
        UserRole.EMPLOYEE,
        date(2024, 5, 6),
    ),
    SeedUser(
        "employee3@x.com",
        "Daniel Lee",
        "Sales",
        "Account Executive",
        UserRole.EMPLOYEE,
        date(2023, 11, 13),
    ),
)

POLICIES: tuple[tuple[str, str], ...] = (
    (
        "Sick Leave Policy",
        "Sick leave provides paid time off when an employee is ill or injured, "
        "or needs to care for an immediate family member who is unwell. "
        "Employees should notify their manager and HR as early as possible on "
        "the first day of absence, ideally before the start of the working day. "
        "A medical certificate is required for absences of three consecutive "
        "working days or more. Sick leave is tracked separately from casual "
        "leave and is available up to twelve days per calendar year. Unused "
        "sick leave does not carry forward. Employees must record their absence "
        "accurately in the HRMS and keep their manager informed of their "
        "expected return date.",
    ),
    (
        "Casual Leave Policy",
        "Casual leave is intended for personal matters that cannot be scheduled "
        "outside working hours. Employees may request casual leave through the "
        "HRMS at least two working days in advance, except in emergencies, "
        "where notice should be given as soon as practicable. Managers approve "
        "requests based on operational needs and team coverage. Each employee "
        "receives twelve casual leave days per calendar year, and requests are "
        "deducted from the available balance once approved. Casual leave may "
        "not be taken during a notice period without HR approval. Unused casual "
        "leave lapses at the end of the year and cannot be exchanged for "
        "payment.",
    ),
    (
        "Attendance Policy",
        "Regular attendance is essential to reliable service delivery and "
        "teamwork. Standard working hours are from 9:00 AM to 5:30 PM, Monday "
        "through Friday, with a thirty-minute break. Employees must check in "
        "and check out through the HRMS each working day. Arrivals after 9:15 "
        "AM are recorded as late unless approved in advance by a manager. "
        "Repeated lateness or unexcused absence may lead to a performance "
        "conversation. Employees who cannot attend work must inform their "
        "manager and apply for the appropriate leave. HR reviews attendance "
        "records monthly and reports persistent issues to department heads.",
    ),
    (
        "Work From Home Policy",
        "Work from home is available to employees whose duties can be performed "
        "effectively outside the office. Employees may request remote work "
        "through the HRMS, normally at least one working day in advance, and "
        "managers approve requests based on role suitability, team coverage, "
        "and business needs. While working remotely, employees must remain "
        "reachable during standard working hours, attend scheduled meetings, "
        "and maintain the same confidentiality and security standards as in "
        "the office. Remote work is not a substitute for leave. Repeated or "
        "unapproved remote days may be treated as absence under the Attendance "
        "Policy.",
    ),
)


def last_weekdays(count: int, end: date | None = None) -> list[date]:
    """Return the last ``count`` weekdays ending today (or ``end``)."""
    current = end or date.today()
    days: list[date] = []
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return list(reversed(days))


def attendance_status(employee_index: int, day_index: int) -> AttendanceStatus:
    """Return a mostly-present pattern with occasional late/absent days."""
    marker = (employee_index * 7 + day_index) % 11
    if marker == 3:
        return AttendanceStatus.ABSENT
    if marker in {7, 9}:
        return AttendanceStatus.LATE
    return AttendanceStatus.PRESENT


def create_attendance(employee: Employee, employee_index: int) -> list[Attendance]:
    """Build seven weekday attendance rows for one employee."""
    rows: list[Attendance] = []
    for day_index, day in enumerate(last_weekdays(7)):
        status = attendance_status(employee_index, day_index)
        check_in: datetime | None = None
        check_out: datetime | None = None

        if status is not AttendanceStatus.ABSENT:
            start_minutes = (
                40 + employee_index * 3
                if status is AttendanceStatus.LATE
                else employee_index * 2
            )
            check_in = datetime.combine(day, time(9, 0)) + timedelta(
                minutes=start_minutes
            )
            check_out = datetime.combine(day, time(17, 30)) + timedelta(
                minutes=employee_index * 4
            )

        rows.append(
            Attendance(
                employee_id=employee.id,
                date=day,
                check_in=check_in,
                check_out=check_out,
                status=status,
            )
        )
    return rows


def create_leave_balances(employee: Employee) -> list[LeaveBalance]:
    """Build the sick and casual allowances for one employee."""
    return [
        LeaveBalance(
            employee_id=employee.id,
            leave_type=LeaveType.SICK,
            total_days=12,
            used_days=0,
        ),
        LeaveBalance(
            employee_id=employee.id,
            leave_type=LeaveType.CASUAL,
            total_days=12,
            used_days=0,
        ),
    ]


def create_pending_leave_requests(employees: list[Employee]) -> list[LeaveRequest]:
    """Build two pending leave requests."""
    today = date.today()
    return [
        LeaveRequest(
            employee_id=employees[2].id,
            leave_type=LeaveType.SICK,
            start_date=today + timedelta(days=7),
            end_date=today + timedelta(days=8),
            reason="Recovering from flu and need rest.",
            status=LeaveStatus.PENDING,
        ),
        LeaveRequest(
            employee_id=employees[4].id,
            leave_type=LeaveType.CASUAL,
            start_date=today + timedelta(days=14),
            end_date=today + timedelta(days=14),
            reason="Family commitment out of town.",
            status=LeaveStatus.PENDING,
        ),
    ]


def seed(db: Session) -> None:
    """Insert development data into an empty database."""
    employees = [
        Employee(
            full_name=spec.full_name,
            email=spec.email,
            department=spec.department,
            designation=spec.designation,
            join_date=spec.join_date,
        )
        for spec in SEED_USERS
    ]
    db.add_all(employees)
    db.flush()

    for spec, employee in zip(SEED_USERS, employees, strict=True):
        db.add(
            User(
                email=spec.email,
                password_hash=hash_password(SEED_PASSWORD),
                role=spec.role,
                employee_id=employee.id,
            )
        )
    db.flush()

    attendance_rows: list[Attendance] = []
    leave_balances: list[LeaveBalance] = []
    for index, employee in enumerate(employees):
        attendance_rows.extend(create_attendance(employee, index))
        leave_balances.extend(create_leave_balances(employee))

    db.add_all(attendance_rows)
    db.add_all(leave_balances)
    db.add_all(create_pending_leave_requests(employees))
    db.add_all(
        Policy(title=title, content=content) for title, content in POLICIES
    )
    db.commit()

    print(
        "Seed complete: "
        f"{len(employees)} users, "
        f"{len(attendance_rows)} attendance rows, "
        f"{len(leave_balances)} leave balances, "
        f"2 leave requests, "
        f"{len(POLICIES)} policies."
    )


def main() -> None:
    """Create the schema and seed data unless users already exist."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        existing_user_id = db.scalar(select(User.id).limit(1))
        if existing_user_id is not None:
            print("Seed skipped: users already exist.")
            return

        try:
            seed(db)
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
