import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import core.db as bot_db
from core.config import settings
from core.models import Base


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Сессия к тестовой базе данных (DATABASE_URL из .env / переменных окружения).

    Перед каждым тестом создаёт все таблицы заново и удаляет их после —
    так тесты не зависят друг от друга и не портят реальные данные.

    Также сбрасывает пул соединений core.db.engine: он создаётся один раз
    при импорте модуля и иначе может остаться "привязан" к циклу событий
    предыдущего теста, что в pytest-asyncio ломает asyncpg с ошибкой
    "another operation is in progress". В боевом боте цикл событий один,
    так что там этой проблемы нет.
    """
    await bot_db.engine.dispose()

    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    await bot_db.engine.dispose()
