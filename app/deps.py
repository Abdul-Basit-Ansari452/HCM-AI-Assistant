"""Shared FastAPI dependencies.

Role checks belong here as dependencies (for example, a ``require_role``
factory) so route handlers stay free of authorization logic.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db

DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
