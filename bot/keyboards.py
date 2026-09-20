from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def options_keyboard(options: list[tuple[str, str]], callback_prefix: str) -> InlineKeyboardMarkup:
    """options: список (значение, подпись на кнопке)."""
    builder = InlineKeyboardBuilder()
    for value, label in options:
        builder.button(text=label, callback_data=f"{callback_prefix}:{value}")
    builder.adjust(1)
    return builder.as_markup()


def multiselect_keyboard(
    options: list[tuple[str, str]],
    selected: set[str],
    callback_prefix: str,
    done_label: str,
    done_callback: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in options:
        marker = "✅ " if value in selected else ""
        builder.button(text=f"{marker}{label}", callback_data=f"{callback_prefix}:{value}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text=done_label, callback_data=done_callback))
    return builder.as_markup()
