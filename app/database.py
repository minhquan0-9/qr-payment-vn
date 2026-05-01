from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args=connect_args,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create tables if they don't exist. Used in dev / SQLite mode.
    For Postgres production, prefer Alembic migrations.
    """
    from app import models  # noqa: F401  ensure models are registered

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
