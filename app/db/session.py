"""
Database session management for MB-Sparrow.
Provides SQLAlchemy session management with Supabase PostgreSQL backend.
"""

import logging
from typing import Generator, Optional
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager

from app.core.settings import get_settings
from app.db.models import Base

logger = logging.getLogger(__name__)


class DatabaseSessionManager:
    """Manages database sessions and connections."""

    def __init__(self):
        self.settings = get_settings()
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._initialize_database()

    def _get_database_url(self) -> str:
        """Get database URL from environment configuration."""
        import os

        # Try to get DATABASE_URL environment variable first
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            return database_url

        # Build URL from individual environment variables
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "mb_sparrow")
        db_user = os.getenv("DB_USER", "postgres")
        db_password = os.getenv("DB_PASSWORD", "postgres")

        # Only use default password in development
        if db_password == "postgres" and os.getenv("ENVIRONMENT") == "production":
            raise ValueError(
                "Database password must be set via DB_PASSWORD environment variable in production"
            )

        # For Supabase, try to construct from Supabase-specific variables
        supabase_url = self.settings.supabase_url
        if supabase_url and supabase_url.startswith("https://"):
            project_id = supabase_url.split("//")[1].split(".")[0]
            supabase_db_password = os.getenv("SUPABASE_DB_PASSWORD")
            if supabase_db_password:
                return f"postgresql://postgres:{supabase_db_password}@db.{project_id}.supabase.co:5432/postgres"

        # Build URL from components
        return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    def _initialize_database(self):
        """Initialize database engine and session factory."""
        try:
            database_url = self._get_database_url()

            # Create engine with connection pooling
            self._engine = create_engine(
                database_url,
                poolclass=StaticPool,
                pool_pre_ping=True,
                pool_recycle=3600,  # 1 hour
                echo=False,  # Set to True for SQL debugging
            )

            # Create session factory
            self._session_factory = sessionmaker(
                bind=self._engine, autocommit=False, autoflush=False
            )

            # Create tables if they don't exist
            Base.metadata.create_all(self._engine)

            logger.info("Database session manager initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    @property
    def engine(self) -> Engine:
        """Get database engine."""
        if not self._engine:
            self._initialize_database()
        assert self._engine is not None
        return self._engine

    def get_session(self) -> Session:
        """Get a new database session."""
        if not self._session_factory:
            self._initialize_database()
        assert self._session_factory is not None
        return self._session_factory()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self):
        """Close the database engine."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None


# Global database session manager
_db_manager: Optional[DatabaseSessionManager] = None


def get_database_manager() -> DatabaseSessionManager:
    """Get or create the global database session manager."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseSessionManager()
    return _db_manager


def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get a database session.
    For use with FastAPI's dependency injection.
    """
    db_manager = get_database_manager()
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()


# For backward compatibility and direct usage
def get_session() -> Session:
    """Get a database session for direct usage."""
    return get_database_manager().get_session()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Get a transactional session scope."""
    with get_database_manager().session_scope() as session:
        yield session
