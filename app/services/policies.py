"""Read-only policy lookup used by the AI assistant."""

from __future__ import annotations

import re
from typing import TypedDict

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Policy


class PolicyMatch(TypedDict):
    """A policy match with content trimmed for an AI tool response."""

    title: str
    content: str


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "are",
        "can",
        "could",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "many",
        "me",
        "much",
        "my",
        "of",
        "on",
        "or",
        "please",
        "policy",
        "policies",
        "should",
        "tell",
        "the",
        "to",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "would",
        "you",
    }
)


def _keywords(query: str) -> list[str]:
    """Return meaningful lowercase terms from a user query."""
    tokens = _TOKEN_PATTERN.findall(query.lower())
    return [
        token
        for token in tokens
        if len(token) > 1 and token not in _STOP_WORDS
    ]


def search_policies(query: str, limit: int = 2) -> list[PolicyMatch]:
    """Return the best keyword matches from the policy table.

    The lookup is intentionally simple and read-only. Titles weigh more than
    body text, and no user-controlled SQL is executed.
    """
    keywords = _keywords(query)
    if not keywords or limit <= 0:
        return []

    with SessionLocal() as db:
        policies = list(db.scalars(select(Policy).order_by(Policy.id)))

        scored: list[tuple[int, int, Policy]] = []
        for policy in policies:
            title = policy.title.lower()
            content = policy.content.lower()
            score = 0
            for keyword in set(keywords):
                if keyword in title:
                    score += 4
                if keyword in content:
                    score += 1
            if score:
                scored.append((score, policy.id, policy))

    scored.sort(key=lambda row: (-row[0], row[1]))
    matches: list[PolicyMatch] = []
    for _score, _policy_id, policy in scored[:limit]:
        content = policy.content.strip()
        if len(content) > 400:
            content = f"{content[:399].rstrip()}…"
        matches.append({"title": policy.title, "content": content})
    return matches
