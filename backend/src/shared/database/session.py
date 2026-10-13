from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.core.settings import settings
from src.shared.database.base import Base as Base  # re-exported — models.py imports Base from here

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    hide_parameters=True,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    async with engine.begin() as conn:
        # Tables are created via Alembic migrations, not here
        # This just verifies the connection
        from sqlalchemy import text
        version = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        if version != "0018":
            raise RuntimeError("Database schema is not current; run alembic upgrade head")


async def get_db() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session


async def commit_or_flush(db: AsyncSession) -> None:
    """Event handlers own a transaction spanning the receipt, violation and alert."""
    if db.info.get("defer_commit"):
        await db.flush()
    else:
        await db.commit()
