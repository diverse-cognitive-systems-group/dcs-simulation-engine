import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

# SQLite:   sqlite+aiosqlite:///./dcs.db
# Postgres: postgresql+asyncpg://user:password@host:port/dbname
DATABASE_URL = os.environ["DATABASE_URL"]

_is_sqlite = DATABASE_URL.startswith("sqlite")

_engine = create_async_engine(
    DATABASE_URL,
    echo=os.environ.get("DATABASE_ECHO", "false").lower() == "true",
    **({} if _is_sqlite else {"pool_size": 10, "max_overflow": 20}),
)

_SessionFactory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession, rolling back on exception and closing on exit."""
    async with _SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine connection pool (call on app shutdown)."""
    await _engine.dispose()
