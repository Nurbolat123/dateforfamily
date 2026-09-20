"""Еженедельный расчёт подборки: кто кому подходит на этой неделе.

Работает только с базой данных (без Telegram) — бот берёт готовый список
уведомлений и сам решает, как их отправить (см. bot/matching_notifications.py).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.matching import Candidate, MatchResult, QuestionAnswer, calculate_match, find_matches
from core.models import Answer, Match, MatchStatus, User, UserStatus
from core.questions import QUESTIONS

MAX_NEW_MATCHES_PER_USER = 5

_QUESTION_LAYER_BY_KEY = {q.key: q.layer.value for q in QUESTIONS}
_TOTAL_QUESTIONS = len(QUESTIONS)


@dataclass(frozen=True)
class MatchNotification:
    """Что нужно отправить одной стороне новой пары в боте."""

    match_id: int
    viewer_tg_id: int
    other_name: str
    other_birth_date: date
    other_city: str
    other_willing_to_relocate: bool
    result: MatchResult


def week_start(today: date | None = None) -> date:
    """Понедельник текущей недели — используется как метка недели в matches.week."""
    today = today or date.today()
    return today - timedelta(days=today.weekday())


async def _load_eligible_candidates(session: AsyncSession) -> tuple[dict[int, User], dict[int, Candidate]]:
    """Пользователи, полностью прошедшие анкету и не заблокированные."""
    users_result = await session.execute(select(User).where(User.status != UserStatus.BLOCKED))
    users_by_id = {u.id: u for u in users_result.scalars().all()}

    answers_result = await session.execute(
        select(Answer).where(Answer.user_id.in_(users_by_id.keys()))
    )
    answers_by_user: dict[int, list[Answer]] = defaultdict(list)
    for answer in answers_result.scalars().all():
        answers_by_user[answer.user_id].append(answer)

    candidates: dict[int, Candidate] = {}
    for user_id, user in users_by_id.items():
        user_answers = answers_by_user.get(user_id, [])
        if len(user_answers) < _TOTAL_QUESTIONS:
            continue  # анкета ещё не завершена

        candidates[user_id] = Candidate(
            user_id=user_id,
            is_blocked=False,
            clan_ru=user.clan_ru,
            answers=tuple(
                QuestionAnswer(
                    question_key=a.question_key,
                    layer=_QUESTION_LAYER_BY_KEY.get(a.question_key, "values"),
                    own_option=a.own_option,
                    acceptable_options=tuple(a.acceptable_options),
                    importance=a.importance,
                )
                for a in user_answers
            ),
        )

    return users_by_id, candidates


async def _load_seen_pairs(session: AsyncSession) -> dict[int, set[int]]:
    """Кто кому уже показывался (в любую неделю) — чтобы не повторяться."""
    result = await session.execute(select(Match.user_a_id, Match.user_b_id))
    seen: dict[int, set[int]] = defaultdict(set)
    for user_a_id, user_b_id in result.all():
        seen[user_a_id].add(user_b_id)
        seen[user_b_id].add(user_a_id)
    return seen


def _notification(match_id: int, viewer: User, other: User, result: MatchResult) -> MatchNotification:
    return MatchNotification(
        match_id=match_id,
        viewer_tg_id=viewer.tg_id,
        other_name=other.name,
        other_birth_date=other.birth_date,
        other_city=other.city,
        other_willing_to_relocate=other.willing_to_relocate,
        result=result,
    )


async def run_weekly_matching(session: AsyncSession) -> list[MatchNotification]:
    """Считает новые пары, сохраняет их в базу и возвращает уведомления для бота.

    Правила (см. CLAUDE.md, "Алгоритм подбора"):
    - не сводить людей одного пола (сервис для создания разнополой семьи);
    - не повторять пары, которые уже были показаны раньше (в любую неделю);
    - не больше MAX_NEW_MATCHES_PER_USER новых кандидатов на человека
      за один запуск, независимо от того, кто из пары был обработан первым.
    """
    users_by_id, candidates_by_id = await _load_eligible_candidates(session)
    seen = await _load_seen_pairs(session)
    new_matches_count: dict[int, int] = defaultdict(int)
    week = week_start()

    notifications: list[MatchNotification] = []

    for user_id in sorted(candidates_by_id):
        if new_matches_count[user_id] >= MAX_NEW_MATCHES_PER_USER:
            continue

        user = users_by_id[user_id]
        already_seen = seen[user_id]

        pool = [
            candidate
            for other_id, candidate in candidates_by_id.items()
            if other_id != user_id
            and other_id not in already_seen
            and new_matches_count[other_id] < MAX_NEW_MATCHES_PER_USER
            and users_by_id[other_id].gender != user.gender
        ]

        remaining_slots = MAX_NEW_MATCHES_PER_USER - new_matches_count[user_id]
        found = find_matches(candidates_by_id[user_id], pool, already_seen=set())[:remaining_slots]

        for candidate, result_for_user in found:
            other_id = candidate.user_id
            if new_matches_count[other_id] >= MAX_NEW_MATCHES_PER_USER:
                continue

            match = Match(
                user_a_id=user_id,
                user_b_id=other_id,
                score=result_for_user.score,
                week=week,
                status_a=MatchStatus.PENDING,
                status_b=MatchStatus.PENDING,
            )
            session.add(match)
            await session.flush()

            result_for_other = calculate_match(candidate, candidates_by_id[user_id])

            notifications.append(_notification(match.id, user, users_by_id[other_id], result_for_user))
            notifications.append(_notification(match.id, users_by_id[other_id], user, result_for_other))

            seen[user_id].add(other_id)
            seen[other_id].add(user_id)
            new_matches_count[user_id] += 1
            new_matches_count[other_id] += 1

            if new_matches_count[user_id] >= MAX_NEW_MATCHES_PER_USER:
                break

    await session.commit()
    return notifications
