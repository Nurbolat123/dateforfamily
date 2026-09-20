"""Расчёт совпадений между анкетами.

Чистые функции без обращения к базе данных — принимают на вход простые
структуры (см. dataclasses ниже), возвращают результат. Это сделано
специально, чтобы алгоритм было легко и быстро тестировать.
"""

from dataclasses import dataclass

# Веса важности ответа (см. CLAUDE.md, "Алгоритм подбора").
IMPORTANCE_WEIGHTS = {
    0: 0,   # неважно
    1: 10,  # важно
    2: 50,  # очень важно
}

# Пары ниже этого порога совпадения не показываются.
MATCH_THRESHOLD = 0.6


@dataclass(frozen=True)
class QuestionAnswer:
    """Ответ одного пользователя на один вопрос анкеты."""

    question_id: int
    layer: str  # "filter" | "values" | "lifestyle"
    own_option: str
    acceptable_options: tuple[str, ...]
    importance: int  # 0, 1 или 2


@dataclass(frozen=True)
class Candidate:
    """Анкета одного пользователя для расчёта подбора."""

    user_id: int
    is_blocked: bool
    clan_ru: str | None
    answers: tuple[QuestionAnswer, ...]

    def answers_by_question(self) -> dict[int, QuestionAnswer]:
        return {a.question_id: a for a in self.answers}


@dataclass(frozen=True)
class MatchExplanation:
    """Объяснение результата: что совпало, а что разошлось."""

    matched_important: list[int]
    mismatched_important: list[int]


@dataclass(frozen=True)
class MatchResult:
    score: float
    explanation: MatchExplanation


def passes_hard_filters(a: Candidate, b: Candidate) -> bool:
    """Проверяет жёсткие фильтры (слой "filter") в обе стороны.

    Пара проходит, только если ответ B устраивает A по всем фильтрам
    A, и наоборот. Вопрос без ответа у одной из сторон не блокирует пару.
    """
    if a.is_blocked or b.is_blocked:
        return False

    a_answers = a.answers_by_question()
    b_answers = b.answers_by_question()

    for question_id, a_answer in a_answers.items():
        if a_answer.layer != "filter":
            continue
        b_answer = b_answers.get(question_id)
        if b_answer is None:
            continue
        if b_answer.own_option not in a_answer.acceptable_options:
            return False

    for question_id, b_answer in b_answers.items():
        if b_answer.layer != "filter":
            continue
        a_answer = a_answers.get(question_id)
        if a_answer is None:
            continue
        if a_answer.own_option not in b_answer.acceptable_options:
            return False

    return True


def directional_score(a: Candidate, b: Candidate) -> float:
    """S(A→B): насколько ответы B устраивают A, с учётом важности для A.

    Считается по всем вопросам, на которые ответил A. Если у A нет ни
    одного ответа (или все "неважно"), сумма весов равна 0 — в этом
    случае направление подбора не может дать вклад в общий результат
    (возвращается 0.0).
    """
    b_answers = b.answers_by_question()

    total_weight = 0
    satisfied_weight = 0

    for question_id, a_answer in a.answers_by_question().items():
        weight = IMPORTANCE_WEIGHTS[a_answer.importance]
        if weight == 0:
            continue
        total_weight += weight

        b_answer = b_answers.get(question_id)
        if b_answer is not None and b_answer.own_option in a_answer.acceptable_options:
            satisfied_weight += weight

    if total_weight == 0:
        return 0.0

    return satisfied_weight / total_weight


def build_explanation(a: Candidate, b: Candidate) -> MatchExplanation:
    """Собирает список важных вопросов, где мнения совпали/разошлись (для A)."""
    b_answers = b.answers_by_question()

    matched: list[int] = []
    mismatched: list[int] = []

    for question_id, a_answer in a.answers_by_question().items():
        if a_answer.importance == 0:
            continue
        b_answer = b_answers.get(question_id)
        if b_answer is None:
            continue
        if b_answer.own_option in a_answer.acceptable_options:
            matched.append(question_id)
        else:
            mismatched.append(question_id)

    return MatchExplanation(matched_important=matched, mismatched_important=mismatched)


def calculate_match(a: Candidate, b: Candidate) -> MatchResult | None:
    """Считает итоговый результат подбора для пары A и B.

    Возвращает None, если пара не проходит жёсткие фильтры или итоговый
    балл ниже порога MATCH_THRESHOLD.
    """
    if not passes_hard_filters(a, b):
        return None

    score_ab = directional_score(a, b)
    score_ba = directional_score(b, a)
    score = (score_ab * score_ba) ** 0.5

    if score < MATCH_THRESHOLD:
        return None

    return MatchResult(score=score, explanation=build_explanation(a, b))


def is_same_clan(a: Candidate, b: Candidate) -> bool:
    """Проверка "жеті ата": принадлежат ли кандидаты к одному роду.

    Используется, только если пользователь сам попросил исключить таких
    кандидатов. Род (clan_ru) нигде не показывается и не участвует в
    обычном подборе.
    """
    if a.clan_ru is None or b.clan_ru is None:
        return False
    return a.clan_ru == b.clan_ru


def find_matches(
    user: Candidate,
    candidates: list[Candidate],
    already_seen: set[int],
    exclude_same_clan: bool = False,
) -> list[tuple[Candidate, MatchResult]]:
    """Ищет подходящих кандидатов для user среди candidates.

    Не включает уже показанных ранее (already_seen — множество user_id).
    Результат отсортирован по убыванию балла.
    """
    results: list[tuple[Candidate, MatchResult]] = []

    for candidate in candidates:
        if candidate.user_id == user.user_id:
            continue
        if candidate.user_id in already_seen:
            continue
        if exclude_same_clan and is_same_clan(user, candidate):
            continue

        match = calculate_match(user, candidate)
        if match is not None:
            results.append((candidate, match))

    results.sort(key=lambda pair: pair[1].score, reverse=True)
    return results
