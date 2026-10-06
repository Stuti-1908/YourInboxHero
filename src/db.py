"""Database configuration with connection pooling."""
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.config.settings import get_settings


def create_engine_with_pooling():
    """Create SQLAlchemy engine with production-ready connection pooling."""
    settings = get_settings()

    # SQLite-specific connect args
    connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=settings.db_pool_pre_ping,
    )
    return engine


engine = create_engine_with_pooling()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency for request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_session():
    """Context-manager for non-FastAPI contexts (workers, functions)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
