from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from bot.keyboards import match_decision_keyboard
from core.db import async_session
from core.format import calculate_age, format_age_ru
from core.locales import option_text, question_text, ui_text
from core.models import MatchStatus
from core.repository import get_match_by_id, get_user_by_id, set_match_side_status
from core.weekly_matching import MatchNotification

router = Router()

LANGUAGE = "ru"  # Казахский появится отдельным шагом (см. CLAUDE.md).


def _format_match_message(notification: MatchNotification) -> str:
    age = calculate_age(notification.other_birth_date)
    relocate_key = "match_relocate_yes" if notification.other_willing_to_relocate else "match_relocate_no"

    lines = [
        ui_text("match_intro", LANGUAGE),
        "",
        f"{notification.other_name}, {format_age_ru(age)}",
        ui_text("match_city_line", LANGUAGE).format(city=notification.other_city),
        ui_text(relocate_key, LANGUAGE),
        "",
        ui_text("match_score_line", LANGUAGE).format(percent=round(notification.result.score * 100)),
    ]

    explanation = notification.result.explanation
    lines.append("")
    lines.append(ui_text("match_matched_header", LANGUAGE))
    if explanation.matched_important:
        for key in explanation.matched_important:
            lines.append(f"— {question_text(key, LANGUAGE)}")
    else:
        lines.append(ui_text("match_no_mismatches", LANGUAGE))

    if explanation.mismatched_important:
        lines.append("")
        lines.append(ui_text("match_mismatched_header", LANGUAGE))
        for key in explanation.mismatched_important:
            lines.append(f"— {question_text(key, LANGUAGE)}")

    return "\n".join(lines)


async def send_match_notifications(bot: Bot, notifications: list[MatchNotification]) -> None:
    for notification in notifications:
        text = _format_match_message(notification)
        keyboard = match_decision_keyboard(
            notification.match_id,
            ui_text("match_interest_button", LANGUAGE),
            ui_text("match_decline_button", LANGUAGE),
        )
        await bot.send_message(notification.viewer_tg_id, text, reply_markup=keyboard)


async def _reveal_contact(bot: Bot, to_tg_id: int, other_tg_id: int, other_name: str) -> None:
    try:
        chat = await bot.get_chat(other_tg_id)
        username = chat.username
    except Exception:
        username = None

    intro = ui_text("mutual_match_intro", LANGUAGE).format(name=other_name)
    if username:
        contact_line = ui_text("mutual_match_contact_username", LANGUAGE).format(username=username)
    else:
        contact_line = ui_text("mutual_match_contact_link", LANGUAGE).format(
            link=f"tg://user?id={other_tg_id}"
        )

    await bot.send_message(to_tg_id, f"{intro}\n{contact_line}")


@router.callback_query(F.data.startswith("match:"))
async def handle_match_decision(callback: CallbackQuery) -> None:
    _, decision, match_id_text = callback.data.split(":", 2)
    match_id = int(match_id_text)

    async with async_session() as session:
        match = await get_match_by_id(session, match_id)

        viewer = None
        is_user_a = None
        for candidate_id, is_a in ((match.user_a_id, True), (match.user_b_id, False)):
            candidate_user = await get_user_by_id(session, candidate_id)
            if candidate_user.tg_id == callback.from_user.id:
                viewer = candidate_user
                is_user_a = is_a

        if viewer is None:
            await callback.answer()
            return

        current_status = match.status_a if is_user_a else match.status_b
        if current_status != MatchStatus.PENDING:
            await callback.answer(ui_text("match_already_decided", LANGUAGE), show_alert=True)
            return

        new_status = MatchStatus.INTERESTED if decision == "interest" else MatchStatus.DECLINED
        await set_match_side_status(session, match, is_user_a=is_user_a, status=new_status)

        other_id = match.user_b_id if is_user_a else match.user_a_id
        other_user = await get_user_by_id(session, other_id)
        mutual = match.status_a == MatchStatus.INTERESTED and match.status_b == MatchStatus.INTERESTED

    await callback.message.edit_reply_markup(reply_markup=None)

    if decision == "decline":
        await callback.message.answer(ui_text("match_declined_ack", LANGUAGE))
    else:
        await callback.message.answer(ui_text("match_interest_ack", LANGUAGE))
        if mutual:
            await _reveal_contact(callback.bot, viewer.tg_id, other_user.tg_id, other_user.name)
            await _reveal_contact(callback.bot, other_user.tg_id, viewer.tg_id, viewer.name)

    await callback.answer()
