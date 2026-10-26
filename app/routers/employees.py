"""Employee routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from app.deps import DbSession, get_current_user, get_optional_user, require_roles
from app.models import Employee, User, UserRole
from app.schemas import EmployeeCreate, EmployeeResponse, EmployeeUpdate
from app.services import employees as employee_service
from app.services.employees import DuplicateEmailError
from app.templating import templates

router = APIRouter(prefix="/employees", tags=["employees"])

AdminOrHr = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.HR)),
]


def _wants_html(request: Request) -> bool:
    """Return True for normal browser navigation requests."""
    return "text/html" in request.headers.get("accept", "")


def employees_list_access(
    request: Request,
    current_user: Annotated[User | None, Depends(get_optional_user)],
) -> User | None:
    """Allow the HTML page shell for any visitor; require admin/hr for JSON."""
    if _wants_html(request):
        return current_user
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if current_user.role not in (UserRole.ADMIN, UserRole.HR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return current_user


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
    request: Request,
    db: DbSession,
    _current_user: Annotated[User | None, Depends(employees_list_access)],
    department: str | None = None,
) -> list[EmployeeResponse] | HTMLResponse:
    """Serve the employees page to browsers, or JSON to API clients."""
    if _wants_html(request):
        return templates.TemplateResponse(request=request, name="employees.html")

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
