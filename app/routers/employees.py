"""Employee routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import DbSession, get_current_user, require_roles
from app.models import Employee, User, UserRole
from app.schemas import EmployeeCreate, EmployeeResponse, EmployeeUpdate
from app.services import employees as employee_service
from app.services.employees import DuplicateEmailError

router = APIRouter(prefix="/employees", tags=["employees"])

AdminOrHr = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.HR)),
]


def get_employee_for_user(
    employee_id: int,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> Employee:
    """Allow admin/hr any employee, and employees only their own record."""
    employee = employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    if current_user.role in (UserRole.ADMIN, UserRole.HR):
        return employee
    if current_user.employee_id == employee.id:
        return employee

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
    )


@router.get("", response_model=list[EmployeeResponse])
def list_employees(
    db: DbSession,
    _current_user: AdminOrHr,
    department: str | None = None,
) -> list[EmployeeResponse]:
    """List employees with an optional department filter."""
    employees = employee_service.list_employees(db, department)
    return [EmployeeResponse.model_validate(employee) for employee in employees]


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee: Annotated[Employee, Depends(get_employee_for_user)],
) -> EmployeeResponse:
    """Return one employee. Employees may only view their own record."""
    return EmployeeResponse.model_validate(employee)


@router.post(
    "",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_employee(
    payload: EmployeeCreate,
    db: DbSession,
    _current_user: AdminOrHr,
) -> EmployeeResponse:
    """Create an employee and linked user with the employee role."""
    try:
        employee, _user = employee_service.create_employee_with_user(
            db,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            department=payload.department,
            designation=payload.designation,
            role=UserRole.EMPLOYEE,
        )
    except DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from None

    return EmployeeResponse.model_validate(employee)


@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: DbSession,
    _current_user: AdminOrHr,
) -> EmployeeResponse:
    """Update employee profile fields. Email cannot be changed."""
    employee = employee_service.update_employee(
        db,
        employee_id,
        full_name=payload.full_name,
        department=payload.department,
        designation=payload.designation,
    )
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    return EmployeeResponse.model_validate(employee)
