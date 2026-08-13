import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.base import Base

# Note: In production, the DATABASE_URL should come from environment variables.
# For now, we default to SQLite in-memory for testing, but can be overridden.
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///:memory:"
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from contextlib import contextmanager

@contextmanager
def get_session():
    """Context-manager that yields a SQLAlchemy session.

    Use this in non-FastAPI contexts (e.g. Azure Function entry points)
    where Depends(get_db) is not available.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()