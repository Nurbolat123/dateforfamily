"""Функции чтения/записи данных о пользователях и ответах анкеты.

Отделены от бота, чтобы этой же логикой позже могло пользоваться
мобильное приложение (см. CLAUDE.md, "Этапы").
"""

from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Answer, Gender, Language, User, UserStatus


async def get_user_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    tg_id: int,
    name: str,
    gender: Gender,
    birth_date: date,
    city: str,
    willing_to_relocate: bool,
    consent_version: str,
    language: Language = Language.RU,
) -> User:
    user = User(
        tg_id=tg_id,
        name=name,
        gender=gender,
        birth_date=birth_date,
        city=city,
        willing_to_relocate=willing_to_relocate,
        status=UserStatus.NEW,
        language=language,
        consent_date=datetime.now(timezone.utc).replace(tzinfo=None),
        consent_version=consent_version,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def renew_consent(session: AsyncSession, user: User, consent_version: str) -> None:
    user.consent_date = datetime.now(timezone.utc).replace(tzinfo=None)
    user.consent_version = consent_version
    await session.commit()


async def get_answered_question_keys(session: AsyncSession, user_id: int) -> set[str]:
    result = await session.execute(select(Answer.question_key).where(Answer.user_id == user_id))
    return set(result.scalars().all())


async def save_answer(
    session: AsyncSession,
    *,
    user_id: int,
    question_key: str,
    own_option: str,
    acceptable_options: list[str],
    importance: int,
) -> None:
    """Сохраняет ответ на вопрос, заменяя предыдущий, если он был.

    Благодаря замене вместо обновления одной и той же строки, повторное
    прохождение анкеты ("изменить ответы") работает без отдельного кода.
    """
    await session.execute(
        delete(Answer).where(Answer.user_id == user_id, Answer.question_key == question_key)
    )
    session.add(
        Answer(
            user_id=user_id,
            question_key=question_key,
            own_option=own_option,
            acceptable_options=acceptable_options,
            importance=importance,
        )
    )
    await session.commit()
