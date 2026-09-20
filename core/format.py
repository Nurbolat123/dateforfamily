"""Мелкие функции форматирования, общие для бота."""

from datetime import date


def calculate_age(birth_date: date, today: date | None = None) -> int:
    today = today or date.today()
    had_birthday_this_year = (today.month, today.day) >= (birth_date.month, birth_date.day)
    return today.year - birth_date.year - (0 if had_birthday_this_year else 1)


def format_age_ru(age: int) -> str:
    """25 -> "25 лет", 21 -> "21 год", 22 -> "22 года"."""
    last_two = age % 100
    last_digit = age % 10

    if 11 <= last_two <= 14:
        word = "лет"
    elif last_digit == 1:
        word = "год"
    elif 2 <= last_digit <= 4:
        word = "года"
    else:
        word = "лет"

    return f"{age} {word}"
