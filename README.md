# HRMS MVP

A small HR management app built with FastAPI, SQLite, Jinja2, and a read-only
LangGraph AI assistant. It covers authentication, employees, attendance, leave,
policy Q&A, a floating AI chat widget, and reviewable AI leave drafting.

## Features

- JWT authentication with role-aware navigation for `admin`, `hr`, and
  `employee` users.
- Dashboard with headcount, attendance, pending leave, and pure-CSS department
  headcount bars.
- Employee directory with admin/HR create and edit flows.
- Attendance history with check-in/check-out actions and daily summaries.
- Leave balances, self-service leave requests, and admin/HR approvals.
- Manual leave form that is always available and has no AI dependency.
- Floating AI assistant on every authenticated page:
  - role-aware example questions;
  - tool-usage badges on every answer;
  - visible `— AI-generated answer` attribution;
  - hourly quota handling and friendly error messages;
  - in-memory conversation history only (cleared on page load).
- Chat-driven leave drafting for employees:
  - ask the assistant for leave in natural language and it prepares a draft;
  - the chat shows type, dates, days, reason, and balance/overlap warnings;
  - `Apply draft to form` stores the draft and opens `/leave`;
  - the leave page shows a review card and `Apply to form` fills the inputs;
  - nothing is submitted until the user clicks `Submit request`.
- Grounded policy Q&A, including work-from-home, leave, and attendance policies.

## Stack

- FastAPI + Uvicorn
- SQLAlchemy 2.x + SQLite
- Pydantic v2 + pydantic-settings
- Jinja2 templates with vanilla CSS/JavaScript
- LangChain, LangGraph, and `langchain-openai`
- `httpx` for the live smoke test

No Docker, Alembic, test framework, or CI is used. Tables are created
automatically at application startup.

## Run from scratch

### 1. Prerequisites

- Python 3.11 or newer
- An OpenAI API key for the AI features
- PowerShell, Command Prompt, or a Unix shell

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation for the current session:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create `.env`

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

Edit `.env` and fill in the values:

```dotenv
OPENAI_API_KEY=sk-your-key-here
JWT_SECRET=replace-with-a-long-random-value
DATABASE_URL=sqlite:///./hrms.db
```

Generate a JWT secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env` is gitignored and must never be committed.

### 5. Seed the database

```bash
python seed.py
```

The seed script is safe to run twice. If users already exist it skips seeding.
To start over, stop the server, delete `hrms.db`, then run `python seed.py`
again.

### 6. Start the app

```bash
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/login>. The healthcheck is
<http://127.0.0.1:8000/health> and returns:

```json
{"status": "ok"}
```

## Test accounts

All seeded accounts use the password `Passw0rd!`.

| Role | Email |
| --- | --- |
| Admin | `admin@x.com` |
| HR | `hr@x.com` |
| Employee | `employee1@x.com` |
| Employee | `employee2@x.com` |
| Employee | `employee3@x.com` |

## AI guardrails

- The assistant is read-only. It cannot insert, update, delete, approve, or
  submit anything.
- All database access goes through a small allow-list of service functions.
  The model never writes SQL and never supplies its own identity.
- Tools are built per request with the authenticated user's role and employee
  id captured in closures.
- Admin/HR-only tools: `headcount`, `attendance_summary`,
  `pending_leave_count`. These are omitted entirely for employees.
- Any-user tools: `my_leave_balance`, `policy_lookup`.
- Employee-only tool: `draft_leave_request`. It validates the parsed draft,
  enriches it with the employee's own balance and existing requests, and returns
  JSON. It never writes a `LeaveRequest`.
- Salary and compensation questions are refused. Salary data is never exposed
  to a tool.
- Answers must be grounded in tool results. The model is instructed not to
  invent numbers or records.
- Every answer ends with the exact line `— AI-generated answer`, enforced by
  the server even if the model omits it.
- The shared per-user quota is 20 AI calls per hour. Exceeding it returns
  `429` with `Hourly AI limit reached (20/hour).`
- AI work has a 15-second timeout and maps provider failures to safe, friendly
  messages.
- Exactly one `AILog` row is written for each executed AI call. Rate-limited
  calls are rejected before any AI work and are not logged.
- `POST /ai/leave/parse` is employee-only. It returns
  `{draft, requested_days, remaining_balance, warnings}`, never creates a
  `LeaveRequest`, and is enriched with insufficient-balance, overlap, and
  past-date warnings from existing read-only services.
- `POST /ai/chat` includes `leave_draft` only when the employee's run invoked
  `draft_leave_request`; otherwise it is `null`.
- The leave form is the only submit path. AI drafting is advisory and requires
  human review.

## Smoke test

The smoke test makes real OpenAI calls and expects a live server. It uses
different seeded users for separate checks so the limit-2 run does not exhaust
one account before the end.

The rate-limit check expects the server to run with `RATE_LIMIT_OVERRIDE=2`.
This variable is for testing only; leave it unset in normal use.

Terminal 1 — start the server with the reduced quota:

Windows PowerShell:

```powershell
$env:RATE_LIMIT_OVERRIDE = "2"
uvicorn app.main:app --reload
```

macOS / Linux:

```bash
RATE_LIMIT_OVERRIDE=2 uvicorn app.main:app --reload
```

Terminal 2 — run the checks:

```bash
python smoke_test.py
```

The default base URL is `http://127.0.0.1:8000`. Override it with
`HRMS_BASE_URL` if needed:

```powershell
$env:HRMS_BASE_URL = "http://127.0.0.1:8010"
python smoke_test.py
```

Expected output ends with:

```text
8/8 checks passed.
```

Checks cover:

1. `GET /health` returns `200`.
2. HR login and `GET /dashboard/summary` return `200`.
3. HR AI chat returns a number with `AI-generated` attribution.
4. Employee AI chat returns a sick-leave balance number.
5. Employee chat drafts sick leave for the correct dates and creates zero
   `LeaveRequest` rows.
6. Employee salary question is refused and contains no digits.
7. Employee leave parse returns an enriched tomorrow/day-after draft.
8. The third AI request returns `429` with a limit of 2.

The rate-limit check uses `admin@x.com`, so run the smoke test against a fresh
seed (or before that account has made recent AI calls). The script never burns
20 calls to discover the limit: it attempts at most three. The draft and salary
checks share `employee2@x.com`, so each stays within the limit-2 quota.

## Project layout

```text
app/
  main.py          # FastAPI app, routes, startup
  config.py        # pydantic-settings configuration
  database.py      # engine, session, Base
  models.py        # SQLAlchemy models
  schemas.py       # Pydantic schemas
  deps.py          # shared dependencies and role checks
  security.py      # password and JWT helpers
  routers/         # HTTP routes
  services/        # business logic and database access
  ai/              # LangGraph agent, tools, prompts, text leave drafting
templates/         # Jinja2 pages and shared layout
static/css/        # design tokens and responsive styles
static/js/         # page behavior, AI chat widget, leave draft review
seed.py            # local development data
smoke_test.py      # live-server acceptance checks
requirements.txt
.env.example
```

## Notes

- The manual leave form works without the AI assistant. AI leave drafting is
  advisory, read-only, and always requires a human review and manual submit.
- AI answers and drafts are generated from HR data and policies. Users should
  review drafts before submitting.
- The app is an MVP: it intentionally has no Docker, migrations, or background
  job system.
