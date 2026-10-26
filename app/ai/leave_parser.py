"""Structured leave-draft extraction for voice input."""

from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from app.config import settings
from app.schemas import LeaveDraft

MODEL_NAME = "gpt-4o-mini"


def build_leave_parser() -> Runnable[Any, LeaveDraft]:
    """Build a model that returns a validated leave draft."""
    model = ChatOpenAI(
        model=MODEL_NAME,
        timeout=15,
        max_retries=1,
        api_key=settings.openai_api_key or None,
    )
    return model.with_structured_output(LeaveDraft)


def build_leave_messages(
    transcript: str,
    today: date,
) -> list[SystemMessage | HumanMessage]:
    """Build the extraction prompt with an explicit reference date."""
    system_prompt = f"""You extract a leave request draft from a spoken transcript.
You are read-only: do not create, approve, reject, save, or submit anything.

Today's date is {today.isoformat()} ({today.strftime("%A")}). Resolve every
relative date from that reference date.

Rules:
- leave_type must be exactly one of: sick, casual, earned. If it is not stated,
  use casual.
- "today" means today's date. "tomorrow" means one day later. "day after
  tomorrow" means two days later.
- "next <weekday>" means the first occurrence of that weekday strictly after
  today. For example, if today is Tuesday, "next Monday" is the Monday six days
  later.
- A bare "<weekday>" means the first occurrence of that weekday on or after
  today.
- When an end date is given as a bare weekday after a start date, use the first
  occurrence of that weekday on or after the start date.
- If only one date is mentioned, use it for both start_date and end_date.
- If no date is mentioned, use today's date for both.
- Dates are inclusive and must be ISO YYYY-MM-DD. end_date must be on or after
  start_date.
- reason must be a short, faithful summary of the stated reason. Preserve key
  details such as "flu" or "family event"; do not invent facts.

Return the four structured fields only.
"""
    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=transcript),
    ]
