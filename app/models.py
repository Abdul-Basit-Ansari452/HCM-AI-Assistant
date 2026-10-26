"""SQLAlchemy 2.x declarative models for the HRMS."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(StrEnum):
    ADMIN = "admin"
    HR = "hr"
    EMPLOYEE = "employee"


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"


class LeaveType(StrEnum):
    SICK = "sick"
    CASUAL = "casual"
    EARNED = "earned"


class LeaveStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def _enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_type]


def _enum_column(enum_type: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=_enum_values,
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(String(80), nullable=False)
    designation: Mapped[str] = mapped_column(String(120), nullable=False)
    join_date: Mapped[date] = mapped_column(Date, nullable=False)

    attendance_records: Mapped[list[Attendance]] = relationship(
        back_populates="employee"
    )
    leave_requests: Mapped[list[LeaveRequest]] = relationship(
        back_populates="employee"
    )
    leave_balances: Mapped[list[LeaveBalance]] = relationship(
        back_populates="employee"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        _enum_column(UserRole, "user_role"), nullable=False
    )
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )

    employee: Mapped[Employee | None] = relationship()
    ai_logs: Mapped[list[AILog]] = relationship(back_populates="user")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_attendance_employee_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    check_in: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_out: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[AttendanceStatus] = mapped_column(
        _enum_column(AttendanceStatus, "attendance_status"), nullable=False
    )

    employee: Mapped[Employee] = relationship(back_populates="attendance_records")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False
    )
    leave_type: Mapped[LeaveType] = mapped_column(
        _enum_column(LeaveType, "leave_type"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[LeaveStatus] = mapped_column(
        _enum_column(LeaveStatus, "leave_request_status"),
        default=LeaveStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    employee: Mapped[Employee] = relationship(back_populates="leave_requests")


class LeaveBalance(Base):
    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "leave_type", name="uq_leave_balance_employee_type"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False
    )
    leave_type: Mapped[LeaveType] = mapped_column(
        _enum_column(LeaveType, "leave_balance_type"), nullable=False
    )
    total_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    employee: Mapped[Employee] = relationship(back_populates="leave_balances")


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class AILog(Base):
    __tablename__ = "ai_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    tools_used: Mapped[str] = mapped_column(Text, default="", nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="ai_logs")


__all__ = [
    "AILog",
    "Attendance",
    "AttendanceStatus",
    "Employee",
    "LeaveBalance",
    "LeaveRequest",
    "LeaveStatus",
    "LeaveType",
    "Policy",
    "User",
    "UserRole",
]
