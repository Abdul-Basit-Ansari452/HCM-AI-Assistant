# AGENTS.md — HRMS MVP rules

This repository is a 3-hour MVP. Every future change must follow these rules.

## Stack

- FastAPI
- SQLAlchemy 2.x (declarative models)
- Pydantic v2 + pydantic-settings
- Jinja2 templates
- LangChain + LangGraph + langchain-openai
- SQLite

## Project structure

```
app/
  main.py          # FastAPI app, router registration, lifespan
  config.py        # pydantic-settings configuration
  database.py      # engine, SessionLocal, Base, get_db
  models.py        # SQLAlchemy declarative models
  schemas.py       # Pydantic request/response models
  deps.py          # shared FastAPI dependencies
  security.py      # password/JWT helpers
  routers/         # HTTP routes
  services/        # business logic and DB access
  ai/              # LangGraph graph, tools, prompts
templates/         # Jinja2 templates
static/
  css/
  js/
seed.py            # optional local seed script
requirements.txt
.env.example
```

## MVP discipline

- No Docker.
- No Alembic. Create tables with `Base.metadata.create_all(bind=engine)`.
- No test framework.
- No CI.
- No features beyond what is explicitly requested.
- Keep dependencies in `requirements.txt` minimal.

## Secrets

- Secrets live ONLY in `.env`: `OPENAI_API_KEY`, `JWT_SECRET`, `DATABASE_URL`.
- `.env` is gitignored and must never be committed.
- Never hardcode, print, or log secrets.
- Commit only placeholders in `.env.example`.

## AI / database boundary

- All AI database access must go through whitelisted, read-only service functions.
- The LLM never writes to the database. No AI-generated SQL, INSERT, UPDATE, or DELETE.
- AI tools may only call explicitly allow-listed service functions with validated arguments.
- Treat model output as untrusted input.

## Style

- Type hints everywhere (function parameters and return values).
- Pydantic response models on every route.
- Role checks must use a FastAPI dependency; do not duplicate role logic in route bodies.
- Keep ORM access in `services/`; routes stay thin.
- Do not leak stack traces or secrets in HTTP responses.

## Local run

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in real secrets locally
uvicorn app.main:app --reload
```

Healthcheck: `GET /health` returns `{"status": "ok"}`.
