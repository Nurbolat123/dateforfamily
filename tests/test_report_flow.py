"""Проверяет кнопку «Пожаловаться» под карточкой кандидата."""

from datetime import date
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.matches import handle_report_reason, handle_report_start
from core.consent import CURRENT_CONSENT_VERSION
from core.models import Gender, UserStatus
from core.questions import QUESTIONS
from core.repository import create_user, list_all_reports, save_answer
from core.weekly_matching import run_weekly_matching

pytestmark = pytest.mark.asyncio


class FakeMessage:
    def __init__(self, text: str | None = None, user_id: int = 0):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.sent: list[str] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.sent.append(text)


class FakeCallbackQuery:
    def __init__(self, data: str, from_user_id: int):
        self.data = data
        self.from_user = SimpleNamespace(id=from_user_id)
        self.message = FakeMessage()

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        pass


def make_state(tg_id: int) -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=0, chat_id=tg_id, user_id=tg_id))


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


async def complete_survey(session, user_id: int) -> None:
    for question in QUESTIONS:
        own_value = question.options[0]
        await save_answer(
            session,
            user_id=user_id,
            question_key=question.key,
            own_option=own_value,
            acceptable_options=[own_value],
            importance=2,
        )


async def test_report_creates_report_row_against_the_other_person(db_session):
    male = await make_user(db_session, 970, Gender.MALE, "Данияр")
    female = await make_user(db_session, 971, Gender.FEMALE, "Айгерим")
    await complete_survey(db_session, male.id)
    await complete_survey(db_session, female.id)

    notifications = await run_weekly_matching(db_session)
    match_id = notifications[0].match_id

    state = make_state(male.tg_id)
    start_cb = FakeCallbackQuery(f"match:report:{match_id}", male.tg_id)
    await handle_report_start(start_cb, state)

    assert "Опишите" in start_cb.message.sent[-1] or "жалоб" in start_cb.message.sent[-1].lower()

    reason_msg = FakeMessage(text="Груб(а) в переписке", user_id=male.tg_id)
    await handle_report_reason(reason_msg, state)

    assert "жалоба" in reason_msg.sent[-1].lower() or "Спасибо" in reason_msg.sent[-1]

    reports = await list_all_reports(db_session)
    assert len(reports) == 1
    assert reports[0].from_user_id == male.id
    assert reports[0].on_user_id == female.id
    assert reports[0].reason == "Груб(а) в переписке"
    assert reports[0].resolved is False

    assert await state.get_state() is None
