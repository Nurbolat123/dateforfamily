import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.formatting import escape
from bot.keyboards import options_keyboard
from bot.states import FeedbackFlow
from core.db import async_session
from core.feedback import FeedbackRequest
from core.locales import ui_text
from core.repository import create_feedback, get_user_by_tg_id

router = Router()
logger = logging.getLogger(__name__)

LANGUAGE = "ru"  # Казахский появится отдельным шагом (см. CLAUDE.md).


async def send_feedback_requests(bot: Bot, requests: list[FeedbackRequest]) -> None:
    for request in requests:
        intro = ui_text("feedback_intro", LANGUAGE).format(name=escape(request.other_name))
        question = ui_text("feedback_met_question", LANGUAGE)
        text = f"{intro}\n{question}"
        keyboard = options_keyboard(
            [("yes", ui_text("yes", LANGUAGE)), ("no", ui_text("no", LANGUAGE))],
            f"feedback:met:{request.match_id}",
        )
        try:
            await bot.send_message(request.viewer_tg_id, text, reply_markup=keyboard)
        except Exception:
            logger.exception("Не удалось отправить запрос отзыва пользователю %s", request.viewer_tg_id)


@router.callback_query(F.data.startswith("feedback:met:"))
async def handle_feedback_met(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, match_id_text, answer = callback.data.split(":", 3)
    met = answer == "yes"

    await state.update_data(feedback_match_id=int(match_id_text), feedback_met=met)
    await callback.message.edit_reply_markup(reply_markup=None)

    if met:
        keyboard = options_keyboard(
            [("yes", ui_text("yes", LANGUAGE)), ("no", ui_text("no", LANGUAGE))],
            f"feedback:liked:{match_id_text}",
        )
        await callback.message.answer(ui_text("feedback_liked_question", LANGUAGE), reply_markup=keyboard)
        await state.set_state(FeedbackFlow.waiting_liked)
    else:
        await callback.message.answer(ui_text("feedback_ask_reason", LANGUAGE))
        await state.set_state(FeedbackFlow.waiting_reason)

    await callback.answer()


@router.callback_query(F.data.startswith("feedback:liked:"))
async def handle_feedback_liked(callback: CallbackQuery, state: FSMContext) -> None:
    answer = callback.data.split(":", 3)[3]
    await state.update_data(feedback_liked=answer == "yes")
    await callback.message.edit_reply_markup(reply_markup=None)

    await callback.message.answer(ui_text("feedback_ask_reason", LANGUAGE))
    await state.set_state(FeedbackFlow.waiting_reason)
    await callback.answer()


@router.message(FeedbackFlow.waiting_reason)
async def handle_feedback_reason(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    data = await state.get_data()

    async with async_session() as session:
        viewer = await get_user_by_tg_id(session, message.from_user.id)
        await create_feedback(
            session,
            match_id=data["feedback_match_id"],
            from_user_id=viewer.id,
            met=data["feedback_met"],
            liked=data.get("feedback_liked"),
            reason=reason,
        )

    await state.clear()
    await message.answer(ui_text("feedback_thanks", LANGUAGE))
