"""Employee business logic and database access."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Employee, User, UserRole
from app.security import hash_password


class DuplicateEmailError(Exception):
    """Raised when an email is already used by an employee or user."""


def create_employee_with_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    department: str,
    designation: str,
    role: UserRole,
) -> tuple[Employee, User]:
    """Create an Employee and its linked User in one transaction."""
    normalized_email = email.strip().lower()

    user_exists = db.scalar(
        select(User.id).where(func.lower(User.email) == normalized_email)
    )
    employee_exists = db.scalar(
        select(Employee.id).where(func.lower(Employee.email) == normalized_email)
    )
    if user_exists is not None or employee_exists is not None:
        raise DuplicateEmailError(normalized_email)

    password_hash = hash_password(password)
    employee = Employee(
        full_name=full_name.strip(),
        email=normalized_email,
        department=department.strip(),
        designation=designation.strip(),
        join_date=date.today(),
    )
    db.add(employee)

    try:
        db.flush()
        user = User(
            email=normalized_email,
            password_hash=password_hash,
            role=role,
            employee_id=employee.id,
        )
        db.add(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateEmailError(normalized_email) from None

    db.refresh(employee)
    db.refresh(user)
    return employee, user


def list_employees(
    db: Session,
    department: str | None = None,
) -> list[Employee]:
    """List employees, optionally filtered by department."""
    statement = select(Employee).order_by(Employee.id)
    if department and department.strip():
        statement = statement.where(
            func.lower(Employee.department) == department.strip().lower()
        )
    return list(db.scalars(statement))


def get_employee(db: Session, employee_id: int) -> Employee | None:
    """Return an employee by id, or None when missing."""
    return db.get(Employee, employee_id)


def update_employee(
    db: Session,
    employee_id: int,
    *,
    full_name: str | None = None,
    department: str | None = None,
    designation: str | None = None,
) -> Employee | None:
    """Update mutable employee fields. Email is intentionally immutable."""
    employee = db.get(Employee, employee_id)
    if employee is None:
        return None

    if full_name is not None:
        employee.full_name = full_name.strip()
    if department is not None:
        employee.department = department.strip()
    if designation is not None:
        employee.designation = designation.strip()

    db.commit()
    db.refresh(employee)
    return employee


def count_employees(department: str | None = None) -> int:
    """Count employees, optionally within a department.

    Kept read-only and self-contained so the AI layer can call it as a tool
    without passing a database session.
    """
    with SessionLocal() as db:
        statement = select(func.count()).select_from(Employee)
        if department and department.strip():
            statement = statement.where(
                func.lower(Employee.department) == department.strip().lower()
            )
        return db.scalar(statement) or 0
