from datetime import date, datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.survey import start_survey_from
from bot.keyboards import options_keyboard
from bot.states import ConsentRenewal, Registration
from core.consent import CONSENT_TEXT_RU, CURRENT_CONSENT_VERSION
from core.db import async_session
from core.locales import ui_text
from core.models import Gender, UserStatus
from core.questions import first_unanswered_index
from core.repository import (
    create_user,
    get_answered_question_keys,
    get_user_by_tg_id,
    renew_consent,
)

router = Router()

LANGUAGE = "ru"  # Казахский появится отдельным шагом (см. CLAUDE.md).
MIN_AGE_YEARS = 18


async def _ask_consent(message: Message, state: FSMContext, renewal: bool) -> None:
    keyboard = options_keyboard(
        [
            ("yes", ui_text("consent_agree", LANGUAGE)),
            ("no", ui_text("consent_decline", LANGUAGE)),
        ],
        "consent",
    )
    await message.answer(CONSENT_TEXT_RU, reply_markup=keyboard)
    await state.set_state(ConsentRenewal.waiting_consent if renewal else Registration.waiting_consent)


async def _show_menu(message: Message) -> None:
    await message.answer(
        ui_text("already_registered", LANGUAGE),
        reply_markup=options_keyboard([("edit", ui_text("menu_edit_answers", LANGUAGE))], "menu"),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()

    async with async_session() as session:
        user = await get_user_by_tg_id(session, message.from_user.id)

    if user is None:
        await message.answer(ui_text("welcome", LANGUAGE))
        await _ask_consent(message, state, renewal=False)
        return

    if user.status == UserStatus.BLOCKED:
        await message.answer(ui_text("blocked", LANGUAGE))
        return

    if user.consent_version != CURRENT_CONSENT_VERSION:
        await message.answer(ui_text("consent_renew_prompt", LANGUAGE))
        await _ask_consent(message, state, renewal=True)
        return

    async with async_session() as session:
        answered = await get_answered_question_keys(session, user.id)

    next_index = first_unanswered_index(answered)
    if next_index is not None:
        await start_survey_from(message, state, start_index=next_index)
        return

    await _show_menu(message)


@router.callback_query(Registration.waiting_consent, F.data.startswith("consent:"))
async def handle_consent(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data == "consent:no":
        await callback.message.answer(ui_text("consent_declined", LANGUAGE))
        await state.clear()
        await callback.answer()
        return

    await callback.message.answer(ui_text("ask_name", LANGUAGE))
    await state.set_state(Registration.waiting_name)
    await callback.answer()


@router.callback_query(ConsentRenewal.waiting_consent, F.data.startswith("consent:"))
async def handle_consent_renewal(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data == "consent:no":
        await callback.message.answer(ui_text("consent_declined", LANGUAGE))
        await state.clear()
        await callback.answer()
        return

    async with async_session() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        await renew_consent(session, user, CURRENT_CONSENT_VERSION)
        answered = await get_answered_question_keys(session, user.id)

    await state.clear()
    next_index = first_unanswered_index(answered)
    if next_index is not None:
        await start_survey_from(callback.message, state, start_index=next_index)
    else:
        await _show_menu(callback.message)
    await callback.answer()


@router.message(Registration.waiting_name)
async def handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(ui_text("invalid_name", LANGUAGE))
        return

    await state.update_data(name=name)
    await message.answer(
        ui_text("ask_gender", LANGUAGE),
        reply_markup=options_keyboard(
            [
                ("male", ui_text("gender_male", LANGUAGE)),
                ("female", ui_text("gender_female", LANGUAGE)),
            ],
            "gender",
        ),
    )
    await state.set_state(Registration.waiting_gender)


@router.callback_query(Registration.waiting_gender, F.data.startswith("gender:"))
async def handle_gender(callback: CallbackQuery, state: FSMContext) -> None:
    gender_value = callback.data.split(":", 1)[1]
    await state.update_data(gender=gender_value)
    await callback.message.answer(ui_text("ask_birth_date", LANGUAGE))
    await state.set_state(Registration.waiting_birth_date)
    await callback.answer()


@router.message(Registration.waiting_birth_date)
async def handle_birth_date(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        birth_date = datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(ui_text("invalid_birth_date", LANGUAGE))
        return

    today = date.today()
    age_years = today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
    if age_years < MIN_AGE_YEARS:
        await message.answer(ui_text("invalid_age", LANGUAGE))
        return

    await state.update_data(birth_date=birth_date.isoformat())
    await message.answer(ui_text("ask_city", LANGUAGE))
    await state.set_state(Registration.waiting_city)


@router.message(Registration.waiting_city)
async def handle_city(message: Message, state: FSMContext) -> None:
    city = (message.text or "").strip()
    if not city:
        await message.answer(ui_text("invalid_city", LANGUAGE))
        return

    await state.update_data(city=city)
    await message.answer(
        ui_text("ask_relocate", LANGUAGE),
        reply_markup=options_keyboard(
            [("yes", ui_text("yes", LANGUAGE)), ("no", ui_text("no", LANGUAGE))],
            "relocate",
        ),
    )
    await state.set_state(Registration.waiting_relocate)


@router.callback_query(Registration.waiting_relocate, F.data.startswith("relocate:"))
async def handle_relocate(callback: CallbackQuery, state: FSMContext) -> None:
    willing_to_relocate = callback.data.split(":", 1)[1] == "yes"
    data = await state.get_data()

    async with async_session() as session:
        await create_user(
            session,
            tg_id=callback.from_user.id,
            name=data["name"],
            gender=Gender(data["gender"]),
            birth_date=date.fromisoformat(data["birth_date"]),
            city=data["city"],
            willing_to_relocate=willing_to_relocate,
            consent_version=CURRENT_CONSENT_VERSION,
        )

    await callback.message.answer(ui_text("registration_done", LANGUAGE))
    await start_survey_from(callback.message, state, start_index=0)
    await callback.answer()


@router.callback_query(F.data == "menu:edit")
async def handle_edit_answers(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer(ui_text("edit_answers_start", LANGUAGE))
    await start_survey_from(callback.message, state, start_index=0)
    await callback.answer()
