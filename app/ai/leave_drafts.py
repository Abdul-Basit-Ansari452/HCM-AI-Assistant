"""Read-only leave-draft creation and enrichment for AI requests.

The assistant may prepare a draft, but only the manual leave form can submit it.
"""

from __future__ import annotations

from datetime import date

from app.ai.date_hints import resolve_relative_dates
from app.ai.leave_parser import build_leave_messages, build_leave_parser
from app.database import SessionLocal
from app.models import LeaveStatus, LeaveType, User
from app.schemas import LeaveDraft, LeaveDraftResult, LeaveDraftWarning
from app.services.leaves import get_leave_balance, list_my_leave_requests


def _plural(count: int, word: str) -> str:
    """Return a simple singular/plural phrase."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _join_leave_types(leave_types: list[str]) -> str:
    """Turn leave type values into a readable list."""
    labels = [leave_type.replace("_", " ").capitalize() for leave_type in leave_types]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} or {labels[-1]}"


def enrich_leave_draft(draft: LeaveDraft, user: User) -> LeaveDraftResult:
    """Add balance, overlap, and past-date warnings without writing anything."""
    employee_id = user.employee_id
    if employee_id is None:
        raise ValueError("This account has no linked employee record.")

    requested_days = (draft.end_date - draft.start_date).days + 1
    parsed_type = LeaveType(draft.leave_type)
    balances = get_leave_balance(employee_id)
    remaining_by_type = {
        row["leave_type"]: row["remaining"] for row in balances
    }
    remaining_balance = remaining_by_type.get(parsed_type, 0)
    warnings: list[LeaveDraftWarning] = []

    if requested_days > remaining_balance:
        other_types = [
            leave_type.value
            for leave_type, remaining in remaining_by_type.items()
            if leave_type != parsed_type and remaining >= requested_days
        ]
        message = (
            f"Only {_plural(remaining_balance, 'day')} of "
            f"{parsed_type.value} leave remain for this "
            f"{_plural(requested_days, 'day')} request."
        )
        if other_types:
            message += f" {_join_leave_types(other_types)} leave could cover it."
        warnings.append(
            LeaveDraftWarning(
                code="insufficient_balance",
                message=message,
                other_leave_types=other_types,
            )
        )

    with SessionLocal() as db:
        overlapping = [
            request
            for request in list_my_leave_requests(db, employee_id)
            if request.status in {LeaveStatus.PENDING, LeaveStatus.APPROVED}
            and request.start_date <= draft.end_date
            and request.end_date >= draft.start_date
        ]
        if overlapping:
            warnings.append(
                LeaveDraftWarning(
                    code="overlap",
                    message=(
                        "This draft overlaps an existing pending or approved "
                        "leave request."
                    ),
                    request_ids=[request.id for request in overlapping],
                )
            )

    if draft.start_date < date.today():
        warnings.append(
            LeaveDraftWarning(
                code="past_date",
                message=(
                    "The start date is in the past. Choose a current or future "
                    "date."
                ),
            )
        )

    return LeaveDraftResult(
        draft=draft,
        requested_days=requested_days,
        remaining_balance=remaining_balance,
        warnings=warnings,
    )


async def draft_leave_from_text(transcript: str, user: User) -> LeaveDraftResult:
    """Parse free text into a validated, enriched draft with no writes."""
    today = date.today()
    parser = build_leave_parser()
    result = await parser.ainvoke(build_leave_messages(transcript, today))
    draft = (
        result
        if isinstance(result, LeaveDraft)
        else LeaveDraft.model_validate(result)
    )

    start, end = resolve_relative_dates(transcript, today)
    if start is not None:
        updates: dict[str, date] = {"start_date": start}
        if end is not None:
            updates["end_date"] = end
        elif draft.end_date < start:
            updates["end_date"] = start
        draft = LeaveDraft.model_validate({**draft.model_dump(), **updates})

    return enrich_leave_draft(draft, user)
