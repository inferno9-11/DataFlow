from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool, StaticPool

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

is_sqlite = "sqlite" in settings.DATABASE_URL.lower()

# Configure Async Engine
engine_kwargs = {
    "echo": settings.DB_ECHO,
    "future": True,
}

if is_sqlite:
    engine_kwargs.update(
        {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool if ":memory:" in settings.DATABASE_URL else NullPool,
        }
    )
else:
    # SQLAlchemy asyncpg automatically wraps QueuePool into AsyncAdaptedQueuePool
    engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_pre_ping": True,
        }
    )

async_engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)
async_session_factory = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Configure Sync Engine (for Celery workers & Alembic)
sync_engine_kwargs = {
    "echo": settings.DB_ECHO,
    "future": True,
}
if is_sqlite:
    sync_engine_kwargs["connect_args"] = {"check_same_thread": False}
    sync_engine_kwargs["poolclass"] = (
        StaticPool if ":memory:" in settings.sync_database_url else NullPool
    )
else:
    sync_engine_kwargs.update(
        {
            "poolclass": QueuePool,
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_pre_ping": True,
        }
    )

sync_engine = create_engine(settings.sync_database_url, **sync_engine_kwargs)
sync_session_factory = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.
    Provides automatic rollback on exception and ensures session is closed.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
