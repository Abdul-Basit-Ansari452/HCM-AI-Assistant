"""AI assistant routes."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from openai import (
    APIConnectionError,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.agent import build_agent
from app.ai.date_hints import relative_date_hint, resolve_relative_dates
from app.ai.leave_drafts import draft_leave_from_text
from app.ai.prompts import ANSWER_SUFFIX
from app.config import settings
from app.deps import DbSession, get_current_user, require_roles
from app.models import User, UserRole
from app.schemas import (
    AIChatRequest,
    AIChatResponse,
    LeaveDraftResult,
    LeaveParseRequest,
)
from app.services.ai_logs import count_recent_calls, create_ai_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

_HOURLY_LIMIT = 20
_AGENT_TIMEOUT_SECONDS = 15
_LEAVE_PARSE_TOOL = "leave_parse"

EmployeeOnly = Annotated[
    User,
    Depends(require_roles(UserRole.EMPLOYEE)),
]


def _content_text(content: Any) -> str:
    """Extract plain text from a LangChain message content payload."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _message_text(message: AIMessage) -> str:
    """Extract plain text from an AI message."""
    return _content_text(message.content)


def _extract_answer(messages: list[Any]) -> str:
    """Return the final non-empty AI message text."""
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            text = _message_text(message)
            if text:
                return text
    return "I could not produce an answer. Please try again."


def _extract_tools_used(messages: list[Any]) -> list[str]:
    """Extract the unique tool names that actually ran."""
    used: list[str] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            name = getattr(message, "name", None)
            if isinstance(name, str) and name and name not in used:
                used.append(name)

    if used:
        return used

    # Compatibility fallback for histories that omit ToolMessage.name.
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in getattr(message, "tool_calls", None) or []:
            if not isinstance(call, dict):
                continue
            name = call.get("name")
            if isinstance(name, str) and name and name not in used:
                used.append(name)
    return used


def _extract_leave_draft(messages: list[Any]) -> LeaveDraftResult | None:
    """Return the last valid draft produced by draft_leave_request."""
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue

        name = getattr(message, "name", None)
        text = _content_text(message.content)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue

        looks_like_draft = {
            "draft",
            "requested_days",
            "warnings",
        }.issubset(payload)
        if name != "draft_leave_request" and not looks_like_draft:
            continue
        try:
            return LeaveDraftResult.model_validate(payload)
        except ValidationError:
            continue
    return None


def _with_footer(answer: str) -> str:
    """Guarantee the required attribution line exactly once at the end."""
    text = (answer or "").strip()
    if not text:
        text = "I could not produce an answer. Please try again."
    if not text.endswith(ANSWER_SUFFIX):
        text = f"{text}\n\n{ANSWER_SUFFIX}"
    return text


def _friendly_error_message(error: Exception) -> str:
    """Map provider failures to safe user-facing messages."""
    if isinstance(error, AuthenticationError):
        return (
            "The AI assistant is not configured correctly. "
            "Please contact an administrator."
        )
    if isinstance(error, RateLimitError):
        return (
            "The AI assistant is receiving too many requests right now. "
            "Please try again in a moment."
        )
    if isinstance(error, APIConnectionError):
        return (
            "The AI assistant cannot reach the provider right now. "
            "Please try again."
        )
    if isinstance(error, OpenAIError):
        return "The AI assistant is temporarily unavailable. Please try again."
    return "The AI assistant is temporarily unavailable. Please try again."


def _hourly_limit() -> int:
    """Return the effective per-user hourly AI quota."""
    override = settings.rate_limit_override
    if override is not None and override > 0:
        return override
    return _HOURLY_LIMIT


def _enforce_rate_limit(db: Session, user: User) -> None:
    """Raise 429 when the user has used the shared hourly AI quota."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    recent_calls = count_recent_calls(
        db,
        user_id=user.id,
        since=cutoff,
    )
    limit = _hourly_limit()
    if recent_calls >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Hourly AI limit reached ({limit}/hour).",
        )


def _log_ai_call(
    db: Session,
    *,
    user_id: int,
    question: str,
    answer: str,
    tools_used: list[str],
    latency_ms: int,
) -> None:
    """Persist one AI call through the service layer."""
    create_ai_log(
        db,
        user_id=user_id,
        question=question,
        answer=answer,
        tools_used=json.dumps(tools_used),
        latency_ms=latency_ms,
    )


@router.post("/chat", response_model=AIChatResponse)
async def chat(
    payload: AIChatRequest,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> AIChatResponse:
    """Answer one read-only HR question for the authenticated user."""
    _enforce_rate_limit(db, current_user)

    started = perf_counter()
    tools_used: list[str] = []
    leave_draft: LeaveDraftResult | None = None
    answer = ""

    try:
        today = date.today()
        resolved_dates = resolve_relative_dates(payload.message, today)
        date_context = relative_date_hint(payload.message, today)
        agent = build_agent(
            current_user,
            date_context=date_context,
            resolved_dates=resolved_dates,
        )
        result = await asyncio.wait_for(
            agent.ainvoke(
                {"messages": [HumanMessage(content=payload.message)]}
            ),
            timeout=_AGENT_TIMEOUT_SECONDS,
        )
        messages = result.get("messages", []) if isinstance(result, dict) else []
        answer = _extract_answer(messages)
        tools_used = _extract_tools_used(messages)
        leave_draft = _extract_leave_draft(messages)
    except TimeoutError:
        answer = "AI is taking too long, please try again."
    except Exception as error:
        if not isinstance(error, OpenAIError):
            logger.warning(
                "AI request failed with %s", type(error).__name__
            )
        answer = _friendly_error_message(error)

    answer = _with_footer(answer)
    latency_ms = max(int((perf_counter() - started) * 1000), 0)
    _log_ai_call(
        db,
        user_id=current_user.id,
        question=payload.message,
        answer=answer,
        tools_used=tools_used,
        latency_ms=latency_ms,
    )

    return AIChatResponse(
        answer=answer,
        tools_used=tools_used,
        leave_draft=leave_draft,
    )


@router.post("/leave/parse", response_model=LeaveDraftResult)
async def parse_leave_text(
    payload: LeaveParseRequest,
    db: DbSession,
    current_user: EmployeeOnly,
) -> LeaveDraftResult:
    """Turn a free-text request into a reviewable leave draft.

    This endpoint is read-only with respect to leave data: it never creates a
    LeaveRequest. The user must submit the prefilled form manually.
    """
    _enforce_rate_limit(db, current_user)

    started = perf_counter()
    draft_result: LeaveDraftResult | None = None
    answer = ""
    failure_status = status.HTTP_502_BAD_GATEWAY

    try:
        draft_result = await asyncio.wait_for(
            draft_leave_from_text(payload.transcript, current_user),
            timeout=_AGENT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        draft_result = None
        answer = "AI is taking too long, please try again."
        failure_status = status.HTTP_504_GATEWAY_TIMEOUT
    except (ValidationError, OutputParserException):
        draft_result = None
        answer = (
            "I couldn't understand the leave dates in that request. "
            "Please try again with clear dates."
        )
        failure_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    except ValueError:
        draft_result = None
        answer = (
            "I couldn't build a valid leave draft. "
            "Please try again with clear dates."
        )
        failure_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    except Exception as error:
        draft_result = None
        if not isinstance(error, OpenAIError):
            logger.warning(
                "Leave parse failed with %s", type(error).__name__
            )
        answer = _friendly_error_message(error)
        failure_status = status.HTTP_502_BAD_GATEWAY

    latency_ms = max(int((perf_counter() - started) * 1000), 0)
    if draft_result is None:
        _log_ai_call(
            db,
            user_id=current_user.id,
            question=payload.transcript,
            answer=answer,
            tools_used=[_LEAVE_PARSE_TOOL],
            latency_ms=latency_ms,
        )
        raise HTTPException(status_code=failure_status, detail=answer)

    _log_ai_call(
        db,
        user_id=current_user.id,
        question=payload.transcript,
        answer=draft_result.model_dump_json(),
        tools_used=[_LEAVE_PARSE_TOOL],
        latency_ms=latency_ms,
    )
    return draft_result
