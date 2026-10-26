"""Dashboard composition built on shared read-only service functions."""

from datetime import date
from typing import TypedDict

from sqlalchemy.orm import Session

from app.models import Attendance, LeaveRequest
from app.services.attendance import attendance_summary, get_my_attendance_today
from app.services.employees import count_employees
from app.services.leaves import (
    LeaveBalanceInfo,
    count_on_leave,
    count_pending_leave_requests,
    get_leave_balance,
    list_my_pending_leave_requests,
)


class DepartmentHeadcount(TypedDict):
    department: str
    count: int


class DashboardSummary(TypedDict):
    total_employees: int
    present_today: int
    late_today: int
    absent_today: int
    on_leave_today: int
    pending_leave_requests: int
    headcount_by_department: list[DepartmentHeadcount]


class MyDashboard(TypedDict):
    my_balances: list[LeaveBalanceInfo]
    my_attendance_today: Attendance | None
    my_pending_requests: list[LeaveRequest]


def get_dashboard_summary() -> DashboardSummary:
    """Build the admin/hr summary from the AI-facing service functions."""
    today = date.today()
    attendance = attendance_summary(today)
    headcount_by_department: list[DepartmentHeadcount] = [
        {
            "department": row["department"],
            "count": count_employees(row["department"]),
        }
        for row in attendance["by_department"]
    ]

    return {
        "total_employees": count_employees(),
        "present_today": attendance["present"],
        "late_today": attendance["late"],
        "absent_today": attendance["absent"],
        "on_leave_today": count_on_leave(today),
        "pending_leave_requests": count_pending_leave_requests(),
        "headcount_by_department": headcount_by_department,
    }


def get_my_dashboard(db: Session, employee_id: int) -> MyDashboard:
    """Build the current employee's dashboard from the shared services."""
    return {
        "my_balances": get_leave_balance(employee_id),
        "my_attendance_today": get_my_attendance_today(db, employee_id),
        "my_pending_requests": list_my_pending_leave_requests(db, employee_id),
    }
