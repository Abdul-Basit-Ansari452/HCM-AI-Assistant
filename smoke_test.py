"""Live smoke test for the HRMS MVP.

Start a live server, then run this script:

    uvicorn app.main:app --reload
    python smoke_test.py

The rate-limit check expects the server to run with ``RATE_LIMIT_OVERRIDE=2``.
It uses the seeded admin account, so run it against a freshly seeded database
or at least before that account has used the AI assistant in the last hour.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import httpx

BASE_URL = os.getenv("HRMS_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
PASSWORD = os.getenv("HRMS_PASSWORD", "Passw0rd!")
HR_EMAIL = os.getenv("HRMS_HR_EMAIL", "hr@x.com")
ADMIN_EMAIL = os.getenv("HRMS_ADMIN_EMAIL", "admin@x.com")
BALANCE_EMAIL = os.getenv("HRMS_BALANCE_EMAIL", "employee1@x.com")
DRAFT_EMAIL = os.getenv("HRMS_DRAFT_EMAIL", "employee2@x.com")
SALARY_EMAIL = os.getenv("HRMS_SALARY_EMAIL", "employee2@x.com")
PARSE_EMAIL = os.getenv("HRMS_PARSE_EMAIL", "employee3@x.com")

CheckResult = tuple[bool, str]
results: list[bool] = []


def auth_headers(token: str) -> dict[str, str]:
    """Return bearer headers for the API."""
    return {"Authorization": f"Bearer {token}"}


def login(client: httpx.Client, email: str) -> str:
    """Log in through the form endpoint and return the access token."""
    response = client.post(
        "/auth/login",
        data={"username": email, "password": PASSWORD},
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("login response did not include access_token")
    return token


def chat(client: httpx.Client, token: str, message: str) -> httpx.Response:
    """Send one AI chat request."""
    return client.post(
        "/ai/chat",
        json={"message": message},
        headers=auth_headers(token),
    )


def contains_number(value: str) -> bool:
    """Accept digits or simple number words in a natural-language answer."""
    if re.search(r"\d", value):
        return True
    number_words = (
        "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    )
    return re.search(rf"\b({number_words})\b", value, re.IGNORECASE) is not None


def next_weekday_after(start: date, weekday: int) -> date:
    """Return the first occurrence of a weekday strictly after ``start``."""
    delta = (weekday - start.weekday()) % 7
    return start + timedelta(days=delta or 7)


def run_check(name: str, action: Callable[[], CheckResult]) -> None:
    """Run one check and print its PASS/FAIL line."""
    try:
        passed, detail = action()
    except Exception as error:  # noqa: BLE001 - smoke tests report all failures
        passed, detail = False, f"{type(error).__name__}: {error}"

    label = "PASS" if passed else "FAIL"
    suffix = f"  [{detail}]" if detail else ""
    print(f"{label}  {name}{suffix}")
    results.append(passed)


def main() -> int:
    """Run every live-server check and return a process exit code."""
    print(f"HRMS smoke test -> {BASE_URL}")
    print("Rate-limit check expects the live server to use RATE_LIMIT_OVERRIDE=2.")

    hr_token: str | None = None

    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        def check_health() -> CheckResult:
            response = client.get("/health")
            if response.status_code != 200:
                return False, f"status={response.status_code}"
            payload: dict[str, Any] = response.json()
            if payload.get("status") != "ok":
                return False, f"body={payload!r}"
            return True, "status=200"

        def check_dashboard() -> CheckResult:
            nonlocal hr_token
            hr_token = login(client, HR_EMAIL)
            response = client.get(
                "/dashboard/summary",
                headers=auth_headers(hr_token),
            )
            if response.status_code != 200:
                return False, f"status={response.status_code}"
            return True, "status=200"

        def check_hr_chat() -> CheckResult:
            if hr_token is None:
                return False, "HR login failed"
            response = chat(
                client,
                hr_token,
                "How many employees are present today?",
            )
            if response.status_code != 200:
                return False, f"status={response.status_code}"
            payload: dict[str, Any] = response.json()
            answer = str(payload.get("answer", ""))
            if "AI-generated" not in answer:
                return False, "answer is missing the AI-generated footer"
            if not contains_number(answer):
                return False, "answer has no number"
            return True, f"tools={payload.get('tools_used', [])}"

        def check_employee_balance() -> CheckResult:
            token = login(client, BALANCE_EMAIL)
            response = chat(
                client,
                token,
                "How many sick leave days do I have left?",
            )
            if response.status_code != 200:
                return False, f"status={response.status_code}"
            payload: dict[str, Any] = response.json()
            answer = str(payload.get("answer", ""))
            if not contains_number(answer):
                return False, "answer has no number"
            return True, f"tools={payload.get('tools_used', [])}"

        def check_employee_chat_draft() -> CheckResult:
            token = login(client, DRAFT_EMAIL)
            before_response = client.get(
                "/leaves/me",
                headers=auth_headers(token),
            )
            if before_response.status_code != 200:
                return False, f"leave list status={before_response.status_code}"
            before_count = len(before_response.json())

            response = chat(
                client,
                token,
                (
                    "I need sick leave from next Monday to Wednesday, "
                    "I have flu"
                ),
            )
            if response.status_code != 200:
                return False, f"status={response.status_code}"

            payload: dict[str, Any] = response.json()
            leave_draft = payload.get("leave_draft")
            if not isinstance(leave_draft, dict):
                return False, f"leave_draft={leave_draft!r}"
            draft = leave_draft.get("draft")
            if not isinstance(draft, dict):
                return False, "leave_draft.draft is missing"
            if "draft_leave_request" not in payload.get("tools_used", []):
                return False, f"tools={payload.get('tools_used', [])}"

            expected_start = next_weekday_after(date.today(), 0)
            expected_end = expected_start + timedelta(
                days=(2 - expected_start.weekday()) % 7
            )
            if draft.get("leave_type") != "sick":
                return False, f"leave_type={draft.get('leave_type')!r}"
            if draft.get("start_date") != expected_start.isoformat():
                return False, (
                    f"start={draft.get('start_date')!r} "
                    f"expected={expected_start.isoformat()!r}"
                )
            if draft.get("end_date") != expected_end.isoformat():
                return False, (
                    f"end={draft.get('end_date')!r} "
                    f"expected={expected_end.isoformat()!r}"
                )
            if "flu" not in str(draft.get("reason", "")).lower():
                return False, f"reason={draft.get('reason')!r}"
            expected_days = (expected_end - expected_start).days + 1
            if leave_draft.get("requested_days") != expected_days:
                return False, f"requested_days={leave_draft.get('requested_days')!r}"
            if not isinstance(leave_draft.get("warnings"), list):
                return False, "warnings is not a list"

            answer = str(payload.get("answer", "")).lower()
            submitted_claims = (
                "has been submitted",
                "was submitted",
                "successfully submitted",
                "i submitted",
                "i've submitted",
                "i have submitted",
            )
            if any(claim in answer for claim in submitted_claims):
                return False, "answer claims the leave was submitted"

            after_response = client.get(
                "/leaves/me",
                headers=auth_headers(token),
            )
            if after_response.status_code != 200:
                return False, f"leave list status={after_response.status_code}"
            after_count = len(after_response.json())
            if after_count != before_count:
                return False, (
                    f"draft created a leave request "
                    f"({before_count}->{after_count})"
                )
            return True, (
                f"{draft.get('start_date')}..{draft.get('end_date')}, "
                f"requests={before_count}"
            )

        def check_salary_refusal() -> CheckResult:
            token = login(client, SALARY_EMAIL)
            response = chat(client, token, "What is Ali's salary?")
            if response.status_code != 200:
                return False, f"status={response.status_code}"
            payload: dict[str, Any] = response.json()
            answer = str(payload.get("answer", ""))
            lowered = answer.lower()
            hints = (
                "salary",
                "out of scope",
                "cannot",
                "can't",
                "unable",
                "not able",
            )
            if not any(hint in lowered for hint in hints):
                return False, "answer does not look like a refusal"
            if re.search(r"\d", answer):
                return False, "refusal contains digits"
            return True, "refused without digits"

        def check_leave_parse() -> CheckResult:
            token = login(client, PARSE_EMAIL)
            response = client.post(
                "/ai/leave/parse",
                json={
                    "transcript": (
                        "I need casual leave tomorrow and the day after, "
                        "family event"
                    )
                },
                headers=auth_headers(token),
            )
            if response.status_code != 200:
                return False, f"status={response.status_code}"
            result: dict[str, Any] = response.json()
            draft = result.get("draft")
            if not isinstance(draft, dict):
                return False, "draft is missing"
            expected_start = date.today() + timedelta(days=1)
            expected_end = expected_start + timedelta(days=1)
            if draft.get("leave_type") != "casual":
                return False, f"leave_type={draft.get('leave_type')!r}"
            if draft.get("start_date") != expected_start.isoformat():
                return False, (
                    f"start={draft.get('start_date')!r} "
                    f"expected={expected_start.isoformat()!r}"
                )
            if draft.get("end_date") != expected_end.isoformat():
                return False, (
                    f"end={draft.get('end_date')!r} "
                    f"expected={expected_end.isoformat()!r}"
                )
            if not str(draft.get("reason", "")).strip():
                return False, "reason is empty"
            if result.get("requested_days") != 2:
                return False, f"requested_days={result.get('requested_days')!r}"
            if not isinstance(result.get("remaining_balance"), int):
                return False, "remaining_balance is not an integer"
            if not isinstance(result.get("warnings"), list):
                return False, "warnings is not a list"
            return True, f"{expected_start.isoformat()}..{expected_end.isoformat()}"

        def check_rate_limit() -> CheckResult:
            token = login(client, ADMIN_EMAIL)
            statuses: list[int] = []
            for message in ("Hello", "Thanks"):
                response = chat(client, token, message)
                statuses.append(response.status_code)
                if response.status_code != 200:
                    return False, (
                        f"statuses={statuses}; admin may have recent AI usage"
                    )

            response = chat(client, token, "Rate limit check")
            statuses.append(response.status_code)
            if response.status_code != 429:
                return False, (
                    f"statuses={statuses}; start the server with "
                    "RATE_LIMIT_OVERRIDE=2"
                )
            payload: dict[str, Any] = response.json()
            if "Hourly AI limit reached" not in str(payload.get("detail", "")):
                return False, f"statuses={statuses}; unexpected detail"
            return True, f"statuses={statuses}"

        run_check("GET /health", check_health)
        run_check("HR login and GET /dashboard/summary", check_dashboard)
        run_check("HR AI chat returns a number with attribution", check_hr_chat)
        run_check("Employee AI chat returns a leave balance number", check_employee_balance)
        run_check(
            "Employee chat drafts sick leave without saving",
            check_employee_chat_draft,
        )
        run_check("Employee salary question is refused without digits", check_salary_refusal)
        run_check(
            "Employee leave parse returns an enriched tomorrow/day-after draft",
            check_leave_parse,
        )
        run_check("AI rate limit returns 429 on the third call", check_rate_limit)

    passed_count = sum(results)
    total_count = len(results)
    print(f"\n{passed_count}/{total_count} checks passed.")
    if passed_count != total_count:
        print("Start the app with a seeded database and RATE_LIMIT_OVERRIDE=2.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
