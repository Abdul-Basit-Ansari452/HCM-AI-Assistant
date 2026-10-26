"""AI request logging and hourly quota helpers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AILog


def count_recent_calls(
    db: Session,
    *,
    user_id: int,
    since: datetime,
) -> int:
    """Count a user's AI calls at or after the supplied cutoff."""
    return (
        db.scalar(
            select(func.count())
            .select_from(AILog)
            .where(AILog.user_id == user_id, AILog.created_at >= since)
        )
        or 0
    )


def create_ai_log(
    db: Session,
    *,
    user_id: int,
    question: str,
    answer: str,
    tools_used: str,
    latency_ms: int,
) -> None:
    """Persist one completed or failed AI request."""
    db.add(
        AILog(
            user_id=user_id,
            question=question,
            answer=answer,
            tools_used=tools_used,
            latency_ms=latency_ms,
        )
    )
    db.commit()
