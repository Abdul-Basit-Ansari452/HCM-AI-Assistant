"""Role-scoped, read-only tools for the HRMS AI assistant.

The LLM never supplies identity. Each tool closes over the authenticated user's
role and linked employee id, and privileged tools are omitted entirely for
employees.
"""

from __future__ import annotations

import json
from datetime import date as Date
from typing import Literal

from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError

from app.ai.leave_drafts import enrich_leave_draft
from app.models import User, UserRole
from app.schemas import LeaveDraft
from app.services.attendance import attendance_summary as get_attendance_summary
from app.services.employees import count_employees
from app.services.leaves import (
    count_pending_leave_requests,
    get_leave_balance,
)
from app.services.policies import search_policies

_HR_ROLES = frozenset({UserRole.ADMIN, UserRole.HR})
_ALL_ROLES = frozenset(UserRole)
_FORBIDDEN = "forbidden: this tool is restricted to HR and admin users."
_FORBIDDEN_EMPLOYEE = "forbidden: this tool is restricted to employees."


def _json(data: object) -> str:
    """Serialize a tool result without leaking non-JSON Python objects."""
    return json.dumps(data, ensure_ascii=False, default=str)


def make_tools_for_user(
    user: User,
    *,
    resolved_dates: tuple[Date | None, Date | None] = (None, None),
) -> list[BaseTool]:
    """Build the tool list for one user, capturing identity in closures."""
    role = user.role
    employee_id = user.employee_id
    resolved_start, resolved_end = resolved_dates

    @tool
    def headcount(department: str | None = None) -> str:
        """Count employees, optionally filtered to one department."""
        if role not in _HR_ROLES:
            return _FORBIDDEN

        scope = department.strip() if department and department.strip() else None
        return _json(
            {
                "department": scope or "all departments",
                "count": count_employees(scope),
            }
        )

    @tool
    def attendance_summary(date: str | None = None) -> str:
        """Get an org-wide attendance summary.

        Omit the date for today's summary. Never guess a date.
        """
        if role not in _HR_ROLES:
            return _FORBIDDEN

        if date is None:
            target_date = Date.today()
        else:
            try:
                target_date = Date.fromisoformat(date.strip())
            except (AttributeError, ValueError):
                return _json(
                    {"error": "Invalid date. Use YYYY-MM-DD, for example 2026-10-27."}
                )

        summary = get_attendance_summary(target_date)
        return _json(
            {
                "date": summary["date"].isoformat(),
                "present": summary["present"],
                "late": summary["late"],
                "absent": summary["absent"],
                "by_department": [
                    {
                        "department": row["department"],
                        "present": row["present"],
                        "total": row["total"],
                    }
                    for row in summary["by_department"]
                ],
            }
        )

    @tool
    def pending_leave_count() -> str:
        """Count pending leave requests across the organization."""
        if role not in _HR_ROLES:
            return _FORBIDDEN

        return _json(
            {"pending_leave_requests": count_pending_leave_requests()}
        )

    @tool
    def draft_leave_request(
        leave_type: Literal["sick", "casual", "earned"],
        start_date: str,
        end_date: str,
        reason: str,
    ) -> str:
        """Draft a leave request for human review. Never saves or submits it."""
        if role != UserRole.EMPLOYEE:
            return _FORBIDDEN_EMPLOYEE
        if employee_id is None:
            return _json(
                {"error": "No linked employee record is available for this user."}
            )
        if resolved_start is not None:
            start_date = resolved_start.isoformat()
        if resolved_end is not None:
            end_date = resolved_end.isoformat()

        try:
            draft = LeaveDraft.model_validate(
                {
                    "leave_type": leave_type,
                    "start_date": start_date,
                    "end_date": end_date,
                    "reason": reason,
                }
            )
        except ValidationError:
            return _json(
                {
                    "error": (
                        "Invalid leave draft. Use leave_type sick, casual, or "
                        "earned; ISO dates (YYYY-MM-DD); and an end date on or "
                        "after the start date."
                    )
                }
            )

        return _json(enrich_leave_draft(draft, user).model_dump(mode="json"))

    @tool
    def my_leave_balance() -> str:
        """Return only the calling user's own leave balances."""
        if role not in _ALL_ROLES:
            return _FORBIDDEN
        if employee_id is None:
            return "No linked employee record is available for this user."

        balances = [
            {
                "leave_type": row["leave_type"].value,
                "total_days": row["total_days"],
                "used_days": row["used_days"],
                "remaining": row["remaining"],
            }
            for row in get_leave_balance(employee_id)
        ]
        return _json(balances)

    @tool
    def policy_lookup(query: str) -> str:
        """Look up the two most relevant HR policy excerpts for a query."""
        if role not in _ALL_ROLES:
            return _FORBIDDEN

        return _json(search_policies(query, limit=2))

    tools: list[BaseTool] = []
    if role in _HR_ROLES:
        tools.extend([headcount, attendance_summary, pending_leave_count])
    if role == UserRole.EMPLOYEE:
        tools.append(draft_leave_request)
    tools.extend([my_leave_balance, policy_lookup])
    return tools
