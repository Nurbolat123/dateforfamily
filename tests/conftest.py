import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import core.db as bot_db
from core.config import settings
from core.models import Base


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Сессия к тестовой базе данных (DATABASE_URL из .env / переменных окружения).

    Таблицы должны быть уже созданы через "alembic upgrade head" — тесты их
    не создают и не удаляют, а только очищают данные до и после каждого
    теста. Так база всегда остаётся в состоянии, которое знает Alembic
    (никаких "ручных правок схемы", как и требует CLAUDE.md), а тесты всё
    равно не влияют друг на друга.

    Также сбрасывает пул соединений core.db.engine: он создаётся один раз
    при импорте модуля и иначе может остаться "привязан" к циклу событий
    предыдущего теста, что в pytest-asyncio ломает asyncpg с ошибкой
    "another operation is in progress". В боевом боте цикл событий один,
    так что там этой проблемы нет.
    """
    await bot_db.engine.dispose()

    engine = create_async_engine(settings.database_url)

    async def clear_all_tables() -> None:
        async with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(table.delete())

    await clear_all_tables()

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await clear_all_tables()
    await engine.dispose()
    await bot_db.engine.dispose()
