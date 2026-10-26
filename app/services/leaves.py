"""Leave business logic and database access."""

from datetime import date
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
)


class InsufficientLeaveBalanceError(Exception):
    """Raised when a request exceeds the employee's remaining balance."""


class OverlappingLeaveError(Exception):
    """Raised when a request overlaps an existing pending/approved request."""


class LeaveNotFoundError(Exception):
    """Raised when a leave request does not exist."""


class LeaveNotPendingError(Exception):
    """Raised when a leave request is no longer pending."""


class LeaveBalanceNotFoundError(Exception):
    """Raised when the matching balance row is missing."""


class LeaveBalanceInfo(TypedDict):
    leave_type: LeaveType
    total_days: int
    used_days: int
    remaining: int


def _inclusive_days(start_date: date, end_date: date) -> int:
    return (end_date - start_date).days + 1


def create_leave_request(
    db: Session,
    *,
    employee_id: int,
    leave_type: LeaveType,
    start_date: date,
    end_date: date,
    reason: str,
) -> LeaveRequest:
    """Create a pending leave request without touching balances."""
    requested_days = _inclusive_days(start_date, end_date)

    balance = db.scalar(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type == leave_type,
        )
    )
    remaining = (
        balance.total_days - balance.used_days if balance is not None else 0
    )
    if requested_days > remaining:
        raise InsufficientLeaveBalanceError

    overlapping = db.scalar(
        select(LeaveRequest.id).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_(
                [LeaveStatus.PENDING, LeaveStatus.APPROVED]
            ),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
    )
    if overlapping is not None:
        raise OverlappingLeaveError

    leave_request = LeaveRequest(
        employee_id=employee_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason.strip(),
        status=LeaveStatus.PENDING,
    )
    db.add(leave_request)
    db.commit()
    db.refresh(leave_request)
    return leave_request


def list_my_leave_requests(
    db: Session,
    employee_id: int,
) -> list[LeaveRequest]:
    """Return an employee's requests, newest first."""
    statement = (
        select(LeaveRequest)
        .where(LeaveRequest.employee_id == employee_id)
        .order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
    )
    return list(db.scalars(statement))


def get_leave_balance(employee_id: int) -> list[LeaveBalanceInfo]:
    """Return per-type balances with remaining days.

    Read-only and self-contained so the AI layer can call it as a tool.
    """
    with SessionLocal() as db:
        balances = db.scalars(
            select(LeaveBalance)
            .where(LeaveBalance.employee_id == employee_id)
            .order_by(LeaveBalance.id)
        ).all()
        return [
            {
                "leave_type": balance.leave_type,
                "total_days": balance.total_days,
                "used_days": balance.used_days,
                "remaining": balance.total_days - balance.used_days,
            }
            for balance in balances
        ]


def list_pending_leave_requests(
    db: Session,
) -> list[tuple[LeaveRequest, Employee]]:
    """Return pending requests with their employees, newest first."""
    rows = db.execute(
        select(LeaveRequest, Employee)
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .where(LeaveRequest.status == LeaveStatus.PENDING)
        .order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
    ).all()
    return [(request, employee) for request, employee in rows]


def approve_leave_request(db: Session, leave_id: int) -> LeaveRequest:
    """Approve a pending request and increment the used balance atomically."""
    leave_request = db.get(LeaveRequest, leave_id)
    if leave_request is None:
        raise LeaveNotFoundError
    if leave_request.status != LeaveStatus.PENDING:
        raise LeaveNotPendingError

    balance = db.scalar(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == leave_request.employee_id,
            LeaveBalance.leave_type == leave_request.leave_type,
        )
    )
    if balance is None:
        raise LeaveBalanceNotFoundError

    try:
        balance.used_days += _inclusive_days(
            leave_request.start_date, leave_request.end_date
        )
        leave_request.status = LeaveStatus.APPROVED
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(leave_request)
    return leave_request


def reject_leave_request(db: Session, leave_id: int) -> LeaveRequest:
    """Reject a pending request without changing balances."""
    leave_request = db.get(LeaveRequest, leave_id)
    if leave_request is None:
        raise LeaveNotFoundError
    if leave_request.status != LeaveStatus.PENDING:
        raise LeaveNotPendingError

    leave_request.status = LeaveStatus.REJECTED
    db.commit()
    db.refresh(leave_request)
    return leave_request
