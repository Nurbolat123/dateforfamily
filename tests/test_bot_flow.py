"""Сквозной тест бота: проходит весь путь пользователя без реального Telegram.

Вызывает обработчики напрямую (это обычные async-функции), подменяя
Message/CallbackQuery простыми объектами-заглушками, но используя настоящую
тестовую базу данных — так же, как это делает core.db в боевом боте.
"""

from datetime import date
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.start import (
    cmd_start,
    handle_birth_date,
    handle_city,
    handle_consent,
    handle_edit_answers,
    handle_gender,
    handle_name,
    handle_relocate,
)
from bot.handlers.survey import (
    handle_acceptable_done,
    handle_importance,
    handle_own_answer,
    handle_toggle_acceptable,
)
from core.questions import QUESTIONS
from core.repository import get_answered_question_keys, get_user_by_tg_id

pytestmark = pytest.mark.asyncio

TG_ID = 555


class FakeMessage:
    def __init__(self, text: str | None = None, user_id: int = TG_ID):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.reply_markup = None
        self.sent: list["FakeMessage"] = []

    async def answer(self, text: str, reply_markup=None) -> "FakeMessage":
        reply = FakeMessage(text=text, user_id=self.from_user.id)
        reply.reply_markup = reply_markup
        self.sent.append(reply)
        return reply

    async def edit_reply_markup(self, reply_markup=None) -> None:
        self.reply_markup = reply_markup


class FakeCallbackQuery:
    def __init__(self, data: str, message: FakeMessage, user_id: int = TG_ID):
        self.data = data
        self.message = message
        self.from_user = SimpleNamespace(id=user_id)
        self.alerts: list[tuple] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.alerts.append((text, show_alert))


def make_state(tg_id: int = TG_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=0, chat_id=tg_id, user_id=tg_id)
    return FSMContext(storage=storage, key=key)


async def register_user(state: FSMContext, tg_id: int = TG_ID) -> FakeMessage:
    """Проходит регистрацию (согласие + профиль) и возвращает сообщение
    с первым вопросом анкеты."""
    start_message = FakeMessage(text="/start", user_id=tg_id)
    await cmd_start(start_message, state)
    consent_prompt = start_message.sent[1]

    consent_cb = FakeCallbackQuery("consent:yes", consent_prompt, user_id=tg_id)
    await handle_consent(consent_cb, state)
    ask_name_msg = consent_prompt.sent[-1]

    name_msg = FakeMessage(text="Айгерим", user_id=tg_id)
    await handle_name(name_msg, state)
    ask_gender_msg = name_msg.sent[-1]

    gender_cb = FakeCallbackQuery("gender:female", ask_gender_msg, user_id=tg_id)
    await handle_gender(gender_cb, state)
    ask_birth_msg = ask_gender_msg.sent[-1]

    birth_msg = FakeMessage(text="05.03.1998", user_id=tg_id)
    await handle_birth_date(birth_msg, state)
    ask_city_msg = birth_msg.sent[-1]

    city_msg = FakeMessage(text="Астана", user_id=tg_id)
    await handle_city(city_msg, state)
    ask_relocate_msg = city_msg.sent[-1]

    relocate_cb = FakeCallbackQuery("relocate:no", ask_relocate_msg, user_id=tg_id)
    await handle_relocate(relocate_cb, state)

    return ask_relocate_msg.sent[-1]


async def answer_question(
    question, prompt_msg: FakeMessage, state: FSMContext, tg_id: int = TG_ID, importance: str = "2"
) -> FakeMessage:
    """Отвечает на один вопрос анкеты (свой ответ -> приемлемые -> важность),
    возвращает сообщение со следующим шагом."""
    own_value = question.options[0]

    own_cb = FakeCallbackQuery(f"survey:own:{own_value}", prompt_msg, user_id=tg_id)
    await handle_own_answer(own_cb, state)
    acceptable_msg = prompt_msg.sent[-1]

    toggle_cb = FakeCallbackQuery(f"survey:acc:{own_value}", acceptable_msg, user_id=tg_id)
    await handle_toggle_acceptable(toggle_cb, state)

    done_cb = FakeCallbackQuery("survey:acc_done", acceptable_msg, user_id=tg_id)
    await handle_acceptable_done(done_cb, state)
    importance_msg = acceptable_msg.sent[-1]

    importance_cb = FakeCallbackQuery(f"survey:imp:{importance}", importance_msg, user_id=tg_id)
    await handle_importance(importance_cb, state)

    return importance_msg.sent[-1]


async def test_full_registration_and_survey_flow(db_session):
    state = make_state()

    own_answer_msg = await register_user(state)

    user = await get_user_by_tg_id(db_session, TG_ID)
    assert user is not None
    assert user.name == "Айгерим"
    assert user.city == "Астана"
    assert user.willing_to_relocate is False

    for question in QUESTIONS:
        own_answer_msg = await answer_question(question, own_answer_msg, state)

    assert "Анкета завершена" in own_answer_msg.text

    answered = await get_answered_question_keys(db_session, user.id)
    assert answered == {q.key for q in QUESTIONS}

    current_state = await state.get_state()
    assert current_state is None


async def test_declining_consent_does_not_create_user(db_session):
    state = make_state(tg_id=601)

    start_message = FakeMessage(text="/start", user_id=601)
    await cmd_start(start_message, state)
    consent_prompt = start_message.sent[1]

    consent_cb = FakeCallbackQuery("consent:no", consent_prompt, user_id=601)
    await handle_consent(consent_cb, state)

    assert "не может" in consent_prompt.sent[-1].text
    assert await get_user_by_tg_id(db_session, 601) is None
    assert await state.get_state() is None


async def test_underage_birth_date_is_rejected_and_can_retry(db_session):
    tg_id = 602
    state = make_state(tg_id=tg_id)

    start_message = FakeMessage(text="/start", user_id=tg_id)
    await cmd_start(start_message, state)
    consent_prompt = start_message.sent[1]

    consent_cb = FakeCallbackQuery("consent:yes", consent_prompt, user_id=tg_id)
    await handle_consent(consent_cb, state)
    ask_name_msg = consent_prompt.sent[-1]

    name_msg = FakeMessage(text="Данияр", user_id=tg_id)
    await handle_name(name_msg, state)
    ask_gender_msg = name_msg.sent[-1]

    gender_cb = FakeCallbackQuery("gender:male", ask_gender_msg, user_id=tg_id)
    await handle_gender(gender_cb, state)
    ask_birth_msg = ask_gender_msg.sent[-1]

    too_young = date.today().replace(year=date.today().year - 15)
    birth_msg = FakeMessage(text=too_young.strftime("%d.%m.%Y"), user_id=tg_id)
    await handle_birth_date(birth_msg, state)

    assert "18 лет" in birth_msg.sent[-1].text
    # Пользователь ещё может ввести дату заново — состояние не сброшено
    assert await state.get_state() == "Registration:waiting_birth_date"


async def test_resume_survey_continues_from_next_question_after_restart(db_session):
    tg_id = 603
    state = make_state(tg_id=tg_id)
    prompt = await register_user(state, tg_id=tg_id)

    # Отвечаем на первые 3 из 15 вопросов, затем "перезапускаем" бота —
    # берём новый FSMContext, как будто пользователь вернулся позже.
    for question in QUESTIONS[:3]:
        prompt = await answer_question(question, prompt, state, tg_id=tg_id)

    fresh_state = make_state(tg_id=tg_id)
    restart_message = FakeMessage(text="/start", user_id=tg_id)
    await cmd_start(restart_message, fresh_state)

    resumed_prompt = restart_message.sent[-1]
    assert QUESTIONS[3].key in resumed_prompt.text or "4" in resumed_prompt.text

    data = await fresh_state.get_data()
    assert data["question_index"] == 3


async def test_edit_answers_restarts_survey_and_overwrites_old_answers(db_session):
    tg_id = 604
    state = make_state(tg_id=tg_id)
    prompt = await register_user(state, tg_id=tg_id)

    for question in QUESTIONS:
        prompt = await answer_question(question, prompt, state, tg_id=tg_id, importance="1")

    user = await get_user_by_tg_id(db_session, tg_id)
    answered_before = await get_answered_question_keys(db_session, user.id)
    assert len(answered_before) == 15

    # Открываем меню и нажимаем "Изменить ответы"
    menu_message = FakeMessage(text="/start", user_id=tg_id)
    await cmd_start(menu_message, state)
    menu_prompt = menu_message.sent[-1]

    edit_cb = FakeCallbackQuery("menu:edit", menu_prompt, user_id=tg_id)
    await handle_edit_answers(edit_cb, state)
    first_question_prompt = menu_prompt.sent[-1]

    # Отвечаем на первый вопрос заново, с другой важностью
    new_prompt = await answer_question(QUESTIONS[0], first_question_prompt, state, tg_id=tg_id, importance="0")

    answered_after = await get_answered_question_keys(db_session, user.id)
    assert len(answered_after) == 15  # старый ответ заменён, а не задвоен
