"""Доступ к текстам анкеты на разных языках.

Использование:
    from core.locales import question_text, option_text
    question_text("smoking", "ru")  -> "Вы курите?"
    option_text("smoking", "does_not_smoke", "ru")  -> "Не курю"
"""

from core.locales import kz, ru

_LANGUAGES = {"ru": ru, "kz": kz}


def question_text(question_key: str, language: str) -> str:
    module = _LANGUAGES[language]
    return module.QUESTIONS[question_key]["text"]


def option_text(question_key: str, option_value: str, language: str) -> str:
    module = _LANGUAGES[language]
    return module.QUESTIONS[question_key]["options"][option_value]
