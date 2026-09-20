"""Кому пора задать вопросы после встречи (см. CLAUDE.md, шаг 7).

Работает только с базой данных, без Telegram — бот сам решает, как
отправить готовый список запросов (см. bot/handlers/feedback.py).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Match, MatchStatus, User

FEEDBACK_DELAY = timedelta(days=3)


@dataclass(frozen=True)
class FeedbackRequest:
    match_id: int
    viewer_tg_id: int
    other_name: str


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def find_due_feedback_requests(session: AsyncSession) -> list[FeedbackRequest]:
    """Находит пары, где взаимный интерес наступил 3+ дня назад, и отмечает,
    что вопрос уже задан (чтобы не спрашивать одного и того же человека
    повторно при следующей проверке).
    """
    cutoff = _now() - FEEDBACK_DELAY

    result = await session.execute(
        select(Match).where(
            Match.status_a == MatchStatus.INTERESTED,
            Match.status_b == MatchStatus.INTERESTED,
            Match.mutual_at.isnot(None),
            Match.mutual_at <= cutoff,
        )
    )
    due_matches = result.scalars().all()

    requests: list[FeedbackRequest] = []
    for match in due_matches:
        if not (match.feedback_requested_a and match.feedback_requested_b):
            user_a = await session.get(User, match.user_a_id)
            user_b = await session.get(User, match.user_b_id)

            if not match.feedback_requested_a:
                requests.append(FeedbackRequest(match.id, user_a.tg_id, user_b.name))
                match.feedback_requested_a = True

            if not match.feedback_requested_b:
                requests.append(FeedbackRequest(match.id, user_b.tg_id, user_a.name))
                match.feedback_requested_b = True

    await session.commit()
    return requests
