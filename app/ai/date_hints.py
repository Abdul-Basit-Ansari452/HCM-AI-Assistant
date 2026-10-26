"""Exact reference dates for resolving relative dates in AI prompts."""

from __future__ import annotations

import re
from datetime import date, timedelta

_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_WEEKDAY_PATTERN = "|".join(weekday.lower() for weekday in _WEEKDAYS)
_RANGE_PATTERN = r"(?:to|until|through|till|and|-|\u2013|\u2014)"
_RELATIVE_RANGE_RE = re.compile(
    rf"\b(?:(next)\s+)?({_WEEKDAY_PATTERN})\b"
    rf"(?:\s*{_RANGE_PATTERN}\s*(?:(next)\s+)?({_WEEKDAY_PATTERN})\b)?",
    re.IGNORECASE,
)
_THIS_WEEKDAY_RE = re.compile(
    rf"\bthis\s+(?:{_WEEKDAY_PATTERN})\b",
    re.IGNORECASE,
)
_LAST_RE = re.compile(r"\blast\b", re.IGNORECASE)


def next_weekday_reference(today: date) -> str:
    """Render exact ISO dates for the next occurrence of each weekday."""
    lines: list[str] = []
    for index, weekday in enumerate(_WEEKDAYS):
        days_ahead = (index - today.weekday()) % 7 or 7
        resolved = today + timedelta(days=days_ahead)
        lines.append(f"- next {weekday}: {resolved.isoformat()}")
    return "\n".join(lines)


def _first_weekday_after(today: date, weekday: int) -> date:
    """Return the first occurrence of a weekday strictly after ``today``."""
    return today + timedelta(days=(weekday - today.weekday()) % 7 or 7)


def _first_weekday_on_or_after(start: date, weekday: int) -> date:
    """Return the first occurrence of a weekday on or after ``start``."""
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def resolve_relative_dates(
    text: str,
    today: date,
) -> tuple[date | None, date | None]:
    """Resolve a clear relative start/end date from free text, when possible."""
    lowered = text.lower()

    # Ambiguous past/this-week phrases and mixed relative days are left to the
    # language model instead of applying an unsafe deterministic override.
    if _THIS_WEEKDAY_RE.search(lowered) or _LAST_RE.search(lowered):
        return None, None

    match = _RELATIVE_RANGE_RE.search(lowered)
    if match:
        start_name = match.group(2)
        start_weekday = _WEEKDAYS.index(start_name.capitalize())
        if match.group(1):
            start = _first_weekday_after(today, start_weekday)
        else:
            start = _first_weekday_on_or_after(today, start_weekday)

        end_name = match.group(4)
        if end_name:
            end_weekday = _WEEKDAYS.index(end_name.capitalize())
            return start, _first_weekday_on_or_after(start, end_weekday)
        if "tomorrow" in lowered or "today" in lowered:
            return None, None
        return start, None

    if "day after tomorrow" in lowered:
        return today + timedelta(days=2), None

    if "tomorrow" in lowered:
        start = today + timedelta(days=1)
        if "day after" in lowered:
            return start, start + timedelta(days=1)
        return start, None

    if "today" in lowered:
        return today, None

    return None, None


def relative_date_hint(text: str, today: date) -> str:
    """Render an authoritative date hint for a user's request."""
    start, end = resolve_relative_dates(text, today)
    if start is None:
        return ""

    lines = [
        "Resolved dates for this request (authoritative; use these exact ISO dates):",
        f"- start_date: {start.isoformat()} ({_WEEKDAYS[start.weekday()]})",
    ]
    if end is not None:
        lines.append(f"- end_date: {end.isoformat()} ({_WEEKDAYS[end.weekday()]})")
    lines.append("Do not recalculate or relabel these dates.")
    return "\n".join(lines)
