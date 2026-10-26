"""Dashboard routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import DbSession, get_current_user, require_roles
from app.models import User, UserRole
from app.schemas import DashboardSummaryResponse, MyDashboardResponse
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

AdminOrHr = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.HR)),
]


@router.get("/summary", response_model=DashboardSummaryResponse)
def summary(_current_user: AdminOrHr) -> DashboardSummaryResponse:
    """Return the admin/hr dashboard summary."""
    return DashboardSummaryResponse.model_validate(
        dashboard_service.get_dashboard_summary()
    )


@router.get("/me", response_model=MyDashboardResponse)
def my_dashboard(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> MyDashboardResponse:
    """Return the current user's dashboard."""
    if current_user.employee_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No linked employee record",
        )
    return MyDashboardResponse.model_validate(
        dashboard_service.get_my_dashboard(db, current_user.employee_id)
    )
