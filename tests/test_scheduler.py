from datetime import date

import pytest

from bot.scheduler import SCHEDULER_KEY, run_matching_if_due
from core.consent import CURRENT_CONSENT_VERSION
from core.models import Gender
from core.questions import QUESTIONS
from core.repository import create_user, get_scheduler_value, save_answer
from core.weekly_matching import week_start

pytestmark = pytest.mark.asyncio


class FakeBot:
    def __init__(self):
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None:
        self.sent_messages.append((chat_id, text))


async def make_matchable_pair(db_session, tg_a: int, tg_b: int):
    a = await create_user(
        db_session,
        tg_id=tg_a,
        name="A",
        gender=Gender.MALE,
        birth_date=date(1998, 3, 5),
        city="Астана",
        willing_to_relocate=False,
        consent_version=CURRENT_CONSENT_VERSION,
    )
    b = await create_user(
        db_session,
        tg_id=tg_b,
        name="B",
        gender=Gender.FEMALE,
        birth_date=date(1998, 3, 5),
        city="Астана",
        willing_to_relocate=False,
        consent_version=CURRENT_CONSENT_VERSION,
    )
    for user in (a, b):
        for question in QUESTIONS:
            own_value = question.options[0]
            await save_answer(
                db_session,
                user_id=user.id,
                question_key=question.key,
                own_option=own_value,
                acceptable_options=[own_value],
                importance=2,
            )
    return a, b


async def test_run_matching_if_due_sends_notifications_and_marks_week(db_session):
    await make_matchable_pair(db_session, 960, 961)
    bot = FakeBot()

    await run_matching_if_due(bot)

    assert len(bot.sent_messages) == 2
    marked_week = await get_scheduler_value(db_session, SCHEDULER_KEY)
    assert marked_week == week_start().isoformat()


async def test_run_matching_if_due_is_a_noop_when_already_run_this_week(db_session):
    await make_matchable_pair(db_session, 962, 963)
    bot = FakeBot()

    await run_matching_if_due(bot)
    first_count = len(bot.sent_messages)
    assert first_count > 0

    await run_matching_if_due(bot)

    assert len(bot.sent_messages) == first_count  # второй прогон ничего не добавил
