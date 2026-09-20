"""Проверяет обработку кнопок «Интересно» / «Не интересно» под кандидатом:
статус пары, взаимный интерес и обмен контактами — без реального Telegram.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from bot.handlers.matches import handle_match_decision
from core.consent import CURRENT_CONSENT_VERSION
from core.models import Gender, MatchStatus
from core.questions import QUESTIONS
from core.repository import create_user, get_match_by_id, save_answer
from core.weekly_matching import run_weekly_matching

pytestmark = pytest.mark.asyncio


class FakeBot:
    def __init__(self, usernames: dict[int, str | None] | None = None):
        self.usernames = usernames or {}
        self.sent_messages: list[tuple[int, str]] = []

    async def get_chat(self, chat_id: int):
        return SimpleNamespace(username=self.usernames.get(chat_id))

    async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None:
        self.sent_messages.append((chat_id, text))


class FakeMessage:
    def __init__(self):
        self.reply_markup = "not_cleared"
        self.sent: list[str] = []

    async def edit_reply_markup(self, reply_markup=None) -> None:
        self.reply_markup = reply_markup

    async def answer(self, text: str, reply_markup=None) -> None:
        self.sent.append(text)


class FakeCallbackQuery:
    def __init__(self, data: str, from_user_id: int, bot: FakeBot):
        self.data = data
        self.from_user = SimpleNamespace(id=from_user_id)
        self.message = FakeMessage()
        self.bot = bot
        self.alerts: list[tuple] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.alerts.append((text, show_alert))


async def make_user(session, tg_id: int, gender: Gender, name: str):
    return await create_user(
        session,
        tg_id=tg_id,
        name=name,
        gender=gender,
        birth_date=date(1998, 3, 5),
        city="Астана",
        willing_to_relocate=False,
        consent_version=CURRENT_CONSENT_VERSION,
    )


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


async def make_match(db_session, male_tg_id=950, female_tg_id=951):
    male = await make_user(db_session, male_tg_id, Gender.MALE, "Данияр")
    female = await make_user(db_session, female_tg_id, Gender.FEMALE, "Айгерим")
    await complete_survey(db_session, male.id)
    await complete_survey(db_session, female.id)

    notifications = await run_weekly_matching(db_session)
    match_id = notifications[0].match_id
    return male, female, match_id


async def test_single_interest_does_not_reveal_contact(db_session):
    male, female, match_id = await make_match(db_session)
    bot = FakeBot(usernames={male.tg_id: "daniyar_tg"})

    callback = FakeCallbackQuery(f"match:interest:{match_id}", male.tg_id, bot)
    await handle_match_decision(callback)

    assert callback.message.reply_markup is None  # кнопки убраны
    assert "интересно" in callback.message.sent[-1].lower() or "Хорошо" in callback.message.sent[-1]
    assert bot.sent_messages == []  # взаимности ещё нет — контакт не раскрыт

    match = await get_match_by_id(db_session, match_id)
    assert match.status_a == MatchStatus.INTERESTED
    assert match.status_b == MatchStatus.PENDING


async def test_mutual_interest_reveals_contact_with_username(db_session):
    male, female, match_id = await make_match(db_session)
    bot = FakeBot(usernames={male.tg_id: "daniyar_tg", female.tg_id: None})

    await handle_match_decision(FakeCallbackQuery(f"match:interest:{match_id}", male.tg_id, bot))
    await handle_match_decision(FakeCallbackQuery(f"match:interest:{match_id}", female.tg_id, bot))

    assert len(bot.sent_messages) == 2
    to_female = next(text for chat_id, text in bot.sent_messages if chat_id == female.tg_id)
    to_male = next(text for chat_id, text in bot.sent_messages if chat_id == male.tg_id)

    assert "@daniyar_tg" in to_female
    assert "tg://user?id=" in to_male  # у female нет username -> ссылка по id

    match = await get_match_by_id(db_session, match_id)
    assert match.status_a == MatchStatus.INTERESTED
    assert match.status_b == MatchStatus.INTERESTED


async def test_decline_does_not_reveal_contact_even_if_other_interested(db_session):
    male, female, match_id = await make_match(db_session)
    bot = FakeBot()

    await handle_match_decision(FakeCallbackQuery(f"match:interest:{match_id}", male.tg_id, bot))
    await handle_match_decision(FakeCallbackQuery(f"match:decline:{match_id}", female.tg_id, bot))

    assert bot.sent_messages == []
    match = await get_match_by_id(db_session, match_id)
    assert match.status_a == MatchStatus.INTERESTED
    assert match.status_b == MatchStatus.DECLINED


async def test_deciding_twice_is_rejected(db_session):
    male, female, match_id = await make_match(db_session)
    bot = FakeBot()

    first = FakeCallbackQuery(f"match:interest:{match_id}", male.tg_id, bot)
    await handle_match_decision(first)

    second = FakeCallbackQuery(f"match:decline:{match_id}", male.tg_id, bot)
    await handle_match_decision(second)

    assert second.alerts and second.alerts[0][1] is True  # show_alert=True
    assert second.message.sent == []  # повторное решение не обработано

    match = await get_match_by_id(db_session, match_id)
    assert match.status_a == MatchStatus.INTERESTED  # не перезаписан на DECLINED
