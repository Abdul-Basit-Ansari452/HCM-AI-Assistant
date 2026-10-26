"""LangGraph agent wiring for the HRMS AI assistant."""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.ai.prompts import build_system_prompt
from app.ai.tools import make_tools_for_user
from app.config import settings
from app.models import User

MODEL_NAME = "gpt-4o-mini"


def build_agent(user: User) -> CompiledStateGraph:
    """Build a fresh role-scoped ReAct agent for one request."""
    model = ChatOpenAI(
        model=MODEL_NAME,
        temperature=0,
        timeout=15,
        max_retries=1,
        api_key=settings.openai_api_key or None,
    )
    return create_react_agent(
        model=model,
        tools=make_tools_for_user(user),
        prompt=build_system_prompt(user),
    )
