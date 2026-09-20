"""Проверяет диалог отзыва в боте: «встретились?» -> «понравилось?» -> «почему?»."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from bot.handlers.feedback import handle_feedback_liked, handle_feedback_met, handle_feedback_reason
from core.consent import CURRENT_CONSENT_VERSION
from core.models import Feedback, Gender, Match, MatchStatus, UserStatus
from core.repository import create_user

pytestmark = pytest.mark.asyncio


class FakeMessage:
    def __init__(self, text: str | None = None, user_id: int = 0):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.reply_markup = "not_cleared"
        self.sent: list[str] = []

    async def edit_reply_markup(self, reply_markup=None) -> None:
        self.reply_markup = reply_markup

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


async def make_mutual_match(session, user_a, user_b) -> Match:
    match = Match(
        user_a_id=user_a.id,
        user_b_id=user_b.id,
        score=0.9,
        week=date.today(),
        status_a=MatchStatus.INTERESTED,
        status_b=MatchStatus.INTERESTED,
        mutual_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=4),
    )
    session.add(match)
    await session.commit()
    await session.refresh(match)
    return match


async def test_full_feedback_flow_when_met_and_liked(db_session):
    male = await make_user(db_session, 1201, Gender.MALE, "Данияр")
    female = await make_user(db_session, 1202, Gender.FEMALE, "Айгерим")
    match = await make_mutual_match(db_session, male, female)

    state = make_state(male.tg_id)

    met_cb = FakeCallbackQuery(f"feedback:met:{match.id}:yes", male.tg_id)
    await handle_feedback_met(met_cb, state)
    assert met_cb.message.reply_markup is None
    assert "понравилась" in met_cb.message.sent[-1].lower()

    liked_cb = FakeCallbackQuery(f"feedback:liked:{match.id}:yes", male.tg_id)
    await handle_feedback_liked(liked_cb, state)
    assert "почему" in liked_cb.message.sent[-1].lower()

    reason_msg = FakeMessage(text="Всё прошло отлично", user_id=male.tg_id)
    await handle_feedback_reason(reason_msg, state)
    assert "Спасибо" in reason_msg.sent[-1]

    result = await db_session.execute(select(Feedback).where(Feedback.match_id == match.id))
    feedback = result.scalar_one()
    assert feedback.from_user_id == male.id
    assert feedback.met is True
    assert feedback.liked is True
    assert feedback.reason == "Всё прошло отлично"

    assert await state.get_state() is None


async def test_feedback_flow_skips_liked_question_when_not_met(db_session):
    male = await make_user(db_session, 1203, Gender.MALE, "Ержан")
    female = await make_user(db_session, 1204, Gender.FEMALE, "Динара")
    match = await make_mutual_match(db_session, male, female)

    state = make_state(female.tg_id)

    met_cb = FakeCallbackQuery(f"feedback:met:{match.id}:no", female.tg_id)
    await handle_feedback_met(met_cb, state)
    assert "почему" in met_cb.message.sent[-1].lower()

    reason_msg = FakeMessage(text="Не получилось договориться о времени", user_id=female.tg_id)
    await handle_feedback_reason(reason_msg, state)

    result = await db_session.execute(select(Feedback).where(Feedback.match_id == match.id))
    feedback = result.scalar_one()
    assert feedback.from_user_id == female.id
    assert feedback.met is False
    assert feedback.liked is None
    assert feedback.reason == "Не получилось договориться о времени"
