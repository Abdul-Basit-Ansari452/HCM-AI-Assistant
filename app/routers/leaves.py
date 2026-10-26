"""Leave routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import DbSession, get_current_user, require_roles
from app.models import LeaveRequest, User, UserRole
from app.schemas import (
    LeaveBalanceResponse,
    LeaveCreate,
    LeaveResponse,
    PendingLeaveResponse,
)
from app.services import leaves as leave_service
from app.services.leaves import (
    InsufficientLeaveBalanceError,
    LeaveBalanceNotFoundError,
    LeaveNotFoundError,
    LeaveNotPendingError,
    OverlappingLeaveError,
)

router = APIRouter(prefix="/leaves", tags=["leaves"])

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


def _leave_response(leave_request: LeaveRequest) -> LeaveResponse:
    return LeaveResponse.model_validate(leave_request)


@router.post(
    "",
    response_model=LeaveResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_leave(
    payload: LeaveCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> LeaveResponse:
    """Create a pending leave request for the current user."""
    employee_id = _linked_employee_id(current_user)
    try:
        leave_request = leave_service.create_leave_request(
            db,
            employee_id=employee_id,
            leave_type=payload.leave_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            reason=payload.reason,
        )
    except (InsufficientLeaveBalanceError, OverlappingLeaveError) as exc:
        detail = (
            "Requested leave exceeds the remaining balance"
            if isinstance(exc, InsufficientLeaveBalanceError)
            else "Request overlaps an existing pending or approved leave"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from None

    return _leave_response(leave_request)


@router.get("/me", response_model=list[LeaveResponse])
def my_leaves(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[LeaveResponse]:
    """Return the current user's leave requests, newest first."""
    employee_id = _linked_employee_id(current_user)
    requests = leave_service.list_my_leave_requests(db, employee_id)
    return [_leave_response(leave_request) for leave_request in requests]


@router.get("/balance/me", response_model=list[LeaveBalanceResponse])
def my_balance(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[LeaveBalanceResponse]:
    """Return the current user's per-type leave balances."""
    employee_id = _linked_employee_id(current_user)
    return [
        LeaveBalanceResponse.model_validate(balance)
        for balance in leave_service.get_leave_balance(employee_id)
    ]


@router.get("/pending", response_model=list[PendingLeaveResponse])
def pending_leaves(
    db: DbSession,
    _current_user: AdminOrHr,
) -> list[PendingLeaveResponse]:
    """Return pending requests with employee details. Admin/hr only."""
    rows = leave_service.list_pending_leave_requests(db)
    return [
        PendingLeaveResponse(
            **LeaveResponse.model_validate(leave_request).model_dump(),
            employee_name=employee.full_name,
            department=employee.department,
        )
        for leave_request, employee in rows
    ]


@router.post("/{leave_id}/approve", response_model=LeaveResponse)
def approve_leave(
    leave_id: int,
    db: DbSession,
    _current_user: AdminOrHr,
) -> LeaveResponse:
    """Approve a pending leave request. Admin/hr only."""
    try:
        leave_request = leave_service.approve_leave_request(db, leave_id)
    except LeaveNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave request not found",
        ) from None
    except LeaveNotPendingError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Leave request is not pending",
        ) from None
    except LeaveBalanceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Leave balance not found",
        ) from None

    return _leave_response(leave_request)


@router.post("/{leave_id}/reject", response_model=LeaveResponse)
def reject_leave(
    leave_id: int,
    db: DbSession,
    _current_user: AdminOrHr,
) -> LeaveResponse:
    """Reject a pending leave request. Admin/hr only."""
    try:
        leave_request = leave_service.reject_leave_request(db, leave_id)
    except LeaveNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave request not found",
        ) from None
    except LeaveNotPendingError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Leave request is not pending",
        ) from None

    return _leave_response(leave_request)
