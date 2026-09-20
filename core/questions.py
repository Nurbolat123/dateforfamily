"""Структура анкеты: вопросы, их слой и варианты ответов.

Здесь хранятся только технические ключи (стабильные идентификаторы),
а не сам текст — тексты для пользователя лежат в core/locales/, отдельно
по языкам. Это позволяет добавить казахский перевод позже, не трогая
структуру анкеты и не переделывая уже посчитанные ответы в базе данных.
"""

from dataclasses import dataclass

from core.models import QuestionLayer


@dataclass(frozen=True)
class QuestionDefinition:
    key: str
    layer: QuestionLayer
    options: tuple[str, ...]


QUESTIONS: tuple[QuestionDefinition, ...] = (
    # --- Слой 1: фильтры (жёсткие) ---
    QuestionDefinition("smoking", QuestionLayer.FILTER, ("smokes", "occasionally", "does_not_smoke")),
    QuestionDefinition("alcohol", QuestionLayer.FILTER, ("drinks", "occasionally", "does_not_drink")),
    QuestionDefinition("employment", QuestionLayer.FILTER, ("works", "studies", "not_working")),
    QuestionDefinition("was_married", QuestionLayer.FILTER, ("yes", "no")),
    QuestionDefinition("has_children", QuestionLayer.FILTER, ("yes", "no")),
    # --- Слой 2: семейные ценности ---
    QuestionDefinition("religiosity", QuestionLayer.VALUES, ("very_religious", "moderately", "not_religious")),
    QuestionDefinition("parents_approval", QuestionLayer.VALUES, ("required", "desirable", "not_required")),
    QuestionDefinition("living_with_parents", QuestionLayer.VALUES, ("separately", "with_parents", "either")),
    QuestionDefinition("wife_works_after_marriage", QuestionLayer.VALUES, ("yes", "no", "if_needed")),
    QuestionDefinition("children_count", QuestionLayer.VALUES, ("one_two", "three_plus", "as_it_happens")),
    # --- Слой 3: образ жизни ---
    QuestionDefinition("money_management", QuestionLayer.LIFESTYLE, ("joint_budget", "separate_budget", "one_manages")),
    QuestionDefinition("household_chores", QuestionLayer.LIFESTYLE, ("shared", "wife_mostly", "husband_helps_a_lot")),
    QuestionDefinition("leisure", QuestionLayer.LIFESTYLE, ("active_outdoors", "home_and_family", "social_gatherings")),
    QuestionDefinition("daily_rhythm", QuestionLayer.LIFESTYLE, ("early_bird", "night_owl", "flexible")),
    QuestionDefinition("conflict_resolution", QuestionLayer.LIFESTYLE, ("talk_immediately", "need_time_alone", "avoid_conflict")),
)


def by_layer(layer: QuestionLayer) -> tuple[QuestionDefinition, ...]:
    return tuple(q for q in QUESTIONS if q.layer == layer)


def by_key(key: str) -> QuestionDefinition:
    for question in QUESTIONS:
        if question.key == key:
            return question
    raise KeyError(f"Неизвестный вопрос анкеты: {key}")
