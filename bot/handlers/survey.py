from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import multiselect_keyboard, options_keyboard
from bot.states import Survey
from core.db import async_session
from core.locales import option_text, question_text, ui_text
from core.questions import QUESTIONS
from core.repository import get_user_by_tg_id, save_answer

router = Router()

LANGUAGE = "ru"  # Казахский появится отдельным шагом (см. CLAUDE.md).


async def start_survey_from(target: Message, state: FSMContext, start_index: int = 0) -> None:
    await state.update_data(question_index=start_index, acceptable_selected=[])
    await _send_own_answer_question(target, state)


async def _send_own_answer_question(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    question = QUESTIONS[data["question_index"]]
    options = [(value, option_text(question.key, value, LANGUAGE)) for value in question.options]

    progress = ui_text("survey_question_progress", LANGUAGE).format(
        current=data["question_index"] + 1, total=len(QUESTIONS)
    )
    text = f"{progress}\n\n{question_text(question.key, LANGUAGE)}"

    await target.answer(text, reply_markup=options_keyboard(options, "survey:own"))
    await state.set_state(Survey.waiting_own_answer)


async def _send_acceptable_question(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    question = QUESTIONS[data["question_index"]]
    selected = set(data.get("acceptable_selected", []))
    options = [(value, option_text(question.key, value, LANGUAGE)) for value in question.options]

    keyboard = multiselect_keyboard(
        options,
        selected,
        "survey:acc",
        ui_text("survey_acceptable_done", LANGUAGE),
        "survey:acc_done",
    )
    await target.answer(ui_text("survey_acceptable_prompt", LANGUAGE), reply_markup=keyboard)
    await state.set_state(Survey.waiting_acceptable_answers)


async def _send_importance_question(target: Message, state: FSMContext) -> None:
    options = [
        ("0", ui_text("importance_0", LANGUAGE)),
        ("1", ui_text("importance_1", LANGUAGE)),
        ("2", ui_text("importance_2", LANGUAGE)),
    ]
    await target.answer(
        ui_text("survey_importance_prompt", LANGUAGE),
        reply_markup=options_keyboard(options, "survey:imp"),
    )
    await state.set_state(Survey.waiting_importance)


@router.callback_query(Survey.waiting_own_answer, F.data.startswith("survey:own:"))
async def handle_own_answer(callback: CallbackQuery, state: FSMContext) -> None:
    own_option = callback.data.split(":", 2)[2]
    await state.update_data(own_option=own_option, acceptable_selected=[])
    await _send_acceptable_question(callback.message, state)
    await callback.answer()


@router.callback_query(Survey.waiting_acceptable_answers, F.data.startswith("survey:acc:"))
async def handle_toggle_acceptable(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 2)[2]
    data = await state.get_data()
    selected = set(data.get("acceptable_selected", []))
    selected.symmetric_difference_update({value})
    await state.update_data(acceptable_selected=list(selected))

    question = QUESTIONS[data["question_index"]]
    options = [(v, option_text(question.key, v, LANGUAGE)) for v in question.options]
    keyboard = multiselect_keyboard(
        options,
        selected,
        "survey:acc",
        ui_text("survey_acceptable_done", LANGUAGE),
        "survey:acc_done",
    )
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


@router.callback_query(Survey.waiting_acceptable_answers, F.data == "survey:acc_done")
async def handle_acceptable_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("acceptable_selected"):
        await callback.answer(ui_text("survey_acceptable_need_one", LANGUAGE), show_alert=True)
        return

    await _send_importance_question(callback.message, state)
    await callback.answer()


@router.callback_query(Survey.waiting_importance, F.data.startswith("survey:imp:"))
async def handle_importance(callback: CallbackQuery, state: FSMContext) -> None:
    importance = int(callback.data.split(":", 2)[2])
    data = await state.get_data()
    question = QUESTIONS[data["question_index"]]

    async with async_session() as session:
        user = await get_user_by_tg_id(session, callback.from_user.id)
        await save_answer(
            session,
            user_id=user.id,
            question_key=question.key,
            own_option=data["own_option"],
            acceptable_options=data.get("acceptable_selected", []),
            importance=importance,
        )

    next_index = data["question_index"] + 1
    if next_index >= len(QUESTIONS):
        await callback.message.answer(ui_text("survey_finished", LANGUAGE))
        await state.clear()
    else:
        await state.update_data(question_index=next_index, acceptable_selected=[])
        await _send_own_answer_question(callback.message, state)

    await callback.answer()
