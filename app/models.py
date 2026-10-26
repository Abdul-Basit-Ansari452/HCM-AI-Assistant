"""SQLAlchemy declarative models.

The scaffold starts without domain tables. Add models here as features are
implemented; import this module before calling ``Base.metadata.create_all``.
"""

from app.database import Base

__all__ = ["Base"]
