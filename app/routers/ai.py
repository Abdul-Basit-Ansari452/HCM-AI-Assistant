"""AI assistant routes."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from openai import (
    APIConnectionError,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)

from app.ai.agent import build_agent
from app.ai.prompts import ANSWER_SUFFIX
from app.deps import DbSession, get_current_user
from app.models import User
from app.schemas import AIChatRequest, AIChatResponse
from app.services.ai_logs import count_recent_calls, create_ai_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

_HOURLY_LIMIT = 20
_AGENT_TIMEOUT_SECONDS = 15


def _message_text(message: AIMessage) -> str:
    """Extract plain text from a LangChain message content payload."""
    content = message.content
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


@router.post("/chat", response_model=AIChatResponse)
async def chat(
    payload: AIChatRequest,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> AIChatResponse:
    """Answer one read-only HR question for the authenticated user."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    recent_calls = count_recent_calls(
        db,
        user_id=current_user.id,
        since=cutoff,
    )
    if recent_calls >= _HOURLY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Hourly AI limit reached (20/hour).",
        )

    started = perf_counter()
    tools_used: list[str] = []
    answer = ""

    try:
        agent = build_agent(current_user)
        result = await asyncio.wait_for(
            agent.ainvoke(
                {"messages": [HumanMessage(content=payload.message)]}
            ),
            timeout=_AGENT_TIMEOUT_SECONDS,
        )
        messages = result.get("messages", []) if isinstance(result, dict) else []
        answer = _extract_answer(messages)
        tools_used = _extract_tools_used(messages)
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
    create_ai_log(
        db,
        user_id=current_user.id,
        question=payload.message,
        answer=answer,
        tools_used=json.dumps(tools_used),
        latency_ms=latency_ms,
    )

    return AIChatResponse(answer=answer, tools_used=tools_used)
