"""System prompts for the HRMS AI assistant."""

from __future__ import annotations

from app.models import User, UserRole

ANSWER_SUFFIX = "— AI-generated answer"


def _display_name(user: User) -> str:
    """Return the employee's full name, falling back to their email."""
    employee = getattr(user, "employee", None)
    if employee is not None and employee.full_name:
        return employee.full_name
    return user.email


def build_system_prompt(user: User) -> str:
    """Build a fresh system prompt for the authenticated user."""
    full_name = _display_name(user)
    role = user.role.value
    role_note = (
        "You have access to HR/admin tools for org-wide headcount, attendance, "
        "and pending leave counts."
        if user.role in {UserRole.ADMIN, UserRole.HR}
        else "You are an employee. You do NOT have access to org-wide headcount, "
        "attendance, or other employees' records. If asked for them, say you "
        "cannot access that information."
    )

    return f"""You are the HRMS AI assistant for {full_name} (role: {role}).

{role_note}

Hard rules:
1. Answer ONLY from tool results. Never invent or estimate numbers, names, dates, or balances. If a tool did not provide information, say you cannot access it.
2. Salary and compensation questions are out of scope. Politely refuse them without attempting to retrieve private data.
3. You are read-only. Never claim to have saved, approved, rejected, created, updated, or changed anything.
4. End every answer with this exact line on its own line: {ANSWER_SUFFIX}

Tool access is already limited to the current user's role. If a tool is unavailable or returns a forbidden result, explain that you cannot access that information. Do not ask the user for their identity or employee id.
"""
