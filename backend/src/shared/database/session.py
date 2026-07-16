from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.core.settings import settings
from src.shared.database.base import Base  # re-exported — models.py imports Base from here

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
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
        await conn.run_sync(lambda _: None)


async def get_db() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session
