"""Create the local SQLite schema.

Usage: python seed.py
"""

import app.models  # noqa: F401  (register models before create_all)
from app.database import Base, engine


def main() -> None:
    """Create all tables defined on Base."""
    Base.metadata.create_all(bind=engine)
    print("Database schema created.")


if __name__ == "__main__":
    main()
