from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

if settings.FASTAPI_ENV == "development":
    engine = create_async_engine(
        str(settings.DATABASE_URL),
        pool_pre_ping=True,
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_maker() as session:
        yield session
