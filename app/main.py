"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401  (register models before create_all)
from app.config import settings
from app.database import Base, engine
from app.routers import (
    ai,
    attendance,
    auth,
    dashboard,
    employees,
    leaves,
)
from app.schemas import HealthResponse
from app.templating import BASE_DIR, templates


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Create the SQLite schema at startup (no Alembic in the MVP)."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(auth.router)
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(leaves.router)
app.include_router(dashboard.router)
app.include_router(ai.router)


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    """Send visitors to the client-side token gate."""
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request) -> HTMLResponse:
    """Serve the login shell."""
    return templates.TemplateResponse(request=request, name="login.html")


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(request: Request) -> HTMLResponse:
    """Serve the dashboard shell; JavaScript chooses the role-specific view."""
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/attendance", response_class=HTMLResponse, include_in_schema=False)
def attendance_page(request: Request) -> HTMLResponse:
    """Serve the attendance shell."""
    return templates.TemplateResponse(request=request, name="attendance.html")


@app.get("/leave", response_class=HTMLResponse, include_in_schema=False)
def leave_page(request: Request) -> HTMLResponse:
    """Serve the leave shell."""
    return templates.TemplateResponse(request=request, name="leaves.html")


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return service liveness."""
    return HealthResponse(status="ok")
