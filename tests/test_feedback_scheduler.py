from datetime import date, datetime, timedelta, timezone

import pytest

from bot.scheduler import run_feedback_requests_if_due
from core.consent import CURRENT_CONSENT_VERSION
from core.models import Gender, Match, MatchStatus, UserStatus
from core.repository import create_user

pytestmark = pytest.mark.asyncio


class FakeBot:
    def __init__(self):
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None:
        self.sent_messages.append((chat_id, text))


async def make_user(session, tg_id: int, gender: Gender, name: str):
    user = await create_user(
        session,
        tg_id=tg_id,
        name=name,
        gender=gender,
        birth_date=date(1998, 3, 5),
        city="Астана",
        willing_to_relocate=False,
        consent_version=CURRENT_CONSENT_VERSION,
    )
    user.status = UserStatus.VERIFIED
    await session.commit()
    return user


async def test_sends_feedback_requests_to_both_sides(db_session):
    male = await make_user(db_session, 1301, Gender.MALE, "Нурлан")
    female = await make_user(db_session, 1302, Gender.FEMALE, "Мадина")
    match = Match(
        user_a_id=male.id,
        user_b_id=female.id,
        score=0.9,
        week=date.today(),
        status_a=MatchStatus.INTERESTED,
        status_b=MatchStatus.INTERESTED,
        mutual_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=4),
    )
    db_session.add(match)
    await db_session.commit()

    bot = FakeBot()
    await run_feedback_requests_if_due(bot)

    recipients = {chat_id for chat_id, _ in bot.sent_messages}
    assert recipients == {male.tg_id, female.tg_id}


async def test_does_not_resend_on_second_check(db_session):
    male = await make_user(db_session, 1303, Gender.MALE, "Арман")
    female = await make_user(db_session, 1304, Gender.FEMALE, "Жанна")
    match = Match(
        user_a_id=male.id,
        user_b_id=female.id,
        score=0.9,
        week=date.today(),
        status_a=MatchStatus.INTERESTED,
        status_b=MatchStatus.INTERESTED,
        mutual_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=4),
    )
    db_session.add(match)
    await db_session.commit()

    bot = FakeBot()
    await run_feedback_requests_if_due(bot)
    first_count = len(bot.sent_messages)
    assert first_count == 2

    await run_feedback_requests_if_due(bot)
    assert len(bot.sent_messages) == first_count
