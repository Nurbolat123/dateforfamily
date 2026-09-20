from datetime import date, datetime, timedelta, timezone

import pytest

from core.consent import CURRENT_CONSENT_VERSION
from core.feedback import find_due_feedback_requests
from core.models import Gender, Match, MatchStatus, UserStatus
from core.repository import create_user

pytestmark = pytest.mark.asyncio


async def make_user(session, tg_id: int, gender: Gender, name: str):
    user = await create_user(
        session,
        tg_id=tg_id,
        name=name,
        gender=gender,
        birth_date=date(1998, 3, 5),
        city="Астана",
        willing_to_relocate=False,
        consent_version=CURRENT_CONSENT_VERSION,
    )
    user.status = UserStatus.VERIFIED
    await session.commit()
    return user


async def make_mutual_match(session, user_a, user_b, mutual_at) -> Match:
    match = Match(
        user_a_id=user_a.id,
        user_b_id=user_b.id,
        score=0.9,
        week=date.today(),
        status_a=MatchStatus.INTERESTED,
        status_b=MatchStatus.INTERESTED,
        mutual_at=mutual_at,
    )
    session.add(match)
    await session.commit()
    await session.refresh(match)
    return match


async def test_requests_feedback_for_both_sides_after_three_days(db_session):
    male = await make_user(db_session, 1101, Gender.MALE, "Данияр")
    female = await make_user(db_session, 1102, Gender.FEMALE, "Айгерим")
    mutual_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=4)
    await make_mutual_match(db_session, male, female, mutual_at)

    requests = await find_due_feedback_requests(db_session)

    viewers = {r.viewer_tg_id: r.other_name for r in requests}
    assert viewers == {1101: "Айгерим", 1102: "Данияр"}


async def test_does_not_request_before_three_days_passed(db_session):
    male = await make_user(db_session, 1103, Gender.MALE, "Ержан")
    female = await make_user(db_session, 1104, Gender.FEMALE, "Динара")
    mutual_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    await make_mutual_match(db_session, male, female, mutual_at)

    requests = await find_due_feedback_requests(db_session)

    assert requests == []


async def test_does_not_request_when_not_mutual(db_session):
    male = await make_user(db_session, 1105, Gender.MALE, "Аслан")
    female = await make_user(db_session, 1106, Gender.FEMALE, "Гульнара")
    match = Match(
        user_a_id=male.id,
        user_b_id=female.id,
        score=0.9,
        week=date.today(),
        status_a=MatchStatus.INTERESTED,
        status_b=MatchStatus.PENDING,
        mutual_at=None,
    )
    db_session.add(match)
    await db_session.commit()

    requests = await find_due_feedback_requests(db_session)

    assert requests == []


async def test_does_not_repeat_already_requested_side(db_session):
    male = await make_user(db_session, 1107, Gender.MALE, "Тимур")
    female = await make_user(db_session, 1108, Gender.FEMALE, "Сауле")
    mutual_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=4)
    await make_mutual_match(db_session, male, female, mutual_at)

    first_run = await find_due_feedback_requests(db_session)
    assert len(first_run) == 2

    second_run = await find_due_feedback_requests(db_session)
    assert second_run == []


async def test_requests_only_the_side_not_yet_asked(db_session):
    male = await make_user(db_session, 1109, Gender.MALE, "Нурлан")
    female = await make_user(db_session, 1110, Gender.FEMALE, "Мадина")
    mutual_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=4)
    match = await make_mutual_match(db_session, male, female, mutual_at)
    match.feedback_requested_a = True
    await db_session.commit()

    requests = await find_due_feedback_requests(db_session)

    assert len(requests) == 1
    assert requests[0].viewer_tg_id == female.tg_id
