from datetime import date

import pytest

from core.consent import CURRENT_CONSENT_VERSION
from core.models import Gender, Match, UserStatus
from core.questions import QUESTIONS
from core.repository import create_user, save_answer
from core.weekly_matching import MAX_NEW_MATCHES_PER_USER, run_weekly_matching

pytestmark = pytest.mark.asyncio


async def make_user(
    session, tg_id: int, gender: Gender, name: str | None = None, status: UserStatus = UserStatus.VERIFIED
):
    user = await create_user(
        session,
        tg_id=tg_id,
        name=name or f"User{tg_id}",
        gender=gender,
        birth_date=date(1998, 3, 5),
        city="Астана",
        willing_to_relocate=False,
        consent_version=CURRENT_CONSENT_VERSION,
    )
    user.status = status
    await session.commit()
    return user


async def complete_survey(session, user_id: int, own_value_index: int = 0) -> None:
    """Отвечает на все 15 вопросов, принимая только точно такой же ответ партнёра."""
    for question in QUESTIONS:
        own_value = question.options[own_value_index % len(question.options)]
        await save_answer(
            session,
            user_id=user_id,
            question_key=question.key,
            own_option=own_value,
            acceptable_options=[own_value],
            importance=2,
        )


async def test_matches_opposite_gender_users_who_completed_survey(db_session):
    male = await make_user(db_session, 701, Gender.MALE)
    female = await make_user(db_session, 702, Gender.FEMALE)
    await complete_survey(db_session, male.id)
    await complete_survey(db_session, female.id)

    notifications = await run_weekly_matching(db_session)

    assert len(notifications) == 2
    viewers = {n.viewer_tg_id for n in notifications}
    assert viewers == {701, 702}

    result = await db_session.execute(Match.__table__.select())
    matches = result.fetchall()
    assert len(matches) == 1


async def test_does_not_match_same_gender_users(db_session):
    a = await make_user(db_session, 703, Gender.FEMALE)
    b = await make_user(db_session, 704, Gender.FEMALE)
    await complete_survey(db_session, a.id)
    await complete_survey(db_session, b.id)

    notifications = await run_weekly_matching(db_session)

    assert notifications == []


async def test_skips_users_with_incomplete_survey(db_session):
    male = await make_user(db_session, 705, Gender.MALE)
    female = await make_user(db_session, 706, Gender.FEMALE)
    await complete_survey(db_session, male.id)
    # female отвечает только на часть вопросов
    await save_answer(
        db_session,
        user_id=female.id,
        question_key=QUESTIONS[0].key,
        own_option=QUESTIONS[0].options[0],
        acceptable_options=[QUESTIONS[0].options[0]],
        importance=2,
    )

    notifications = await run_weekly_matching(db_session)

    assert notifications == []


async def test_skips_blocked_users(db_session):
    male = await make_user(db_session, 707, Gender.MALE)
    female = await make_user(db_session, 708, Gender.FEMALE, status=UserStatus.BLOCKED)
    await complete_survey(db_session, male.id)
    await complete_survey(db_session, female.id)

    notifications = await run_weekly_matching(db_session)

    assert notifications == []


async def test_skips_users_not_yet_verified_by_admin(db_session):
    male = await make_user(db_session, 711, Gender.MALE)
    female = await make_user(db_session, 712, Gender.FEMALE, status=UserStatus.NEW)
    await complete_survey(db_session, male.id)
    await complete_survey(db_session, female.id)

    notifications = await run_weekly_matching(db_session)

    assert notifications == []


async def test_does_not_repeat_previously_seen_pair(db_session):
    male = await make_user(db_session, 709, Gender.MALE)
    female = await make_user(db_session, 710, Gender.FEMALE)
    await complete_survey(db_session, male.id)
    await complete_survey(db_session, female.id)

    first_run = await run_weekly_matching(db_session)
    assert len(first_run) == 2

    second_run = await run_weekly_matching(db_session)
    assert second_run == []


async def test_caps_new_matches_per_user_per_run(db_session):
    # Один мужчина совместим с семью женщинами — должно быть создано не
    # больше MAX_NEW_MATCHES_PER_USER пар с его участием за один запуск.
    male = await make_user(db_session, 800, Gender.MALE)
    await complete_survey(db_session, male.id)

    females = []
    for i in range(MAX_NEW_MATCHES_PER_USER + 2):
        female = await make_user(db_session, 801 + i, Gender.FEMALE)
        await complete_survey(db_session, female.id)
        females.append(female)

    notifications = await run_weekly_matching(db_session)

    male_notifications = [n for n in notifications if n.viewer_tg_id == male.tg_id]
    assert len(male_notifications) == MAX_NEW_MATCHES_PER_USER


async def test_notification_contains_explanation_and_profile_fields(db_session):
    male = await make_user(db_session, 900, Gender.MALE, name="Данияр")
    female = await make_user(db_session, 901, Gender.FEMALE, name="Айгерим")
    await complete_survey(db_session, male.id)
    await complete_survey(db_session, female.id)

    notifications = await run_weekly_matching(db_session)

    male_view = next(n for n in notifications if n.viewer_tg_id == 900)
    assert male_view.other_name == "Айгерим"
    assert male_view.other_city == "Астана"
    assert male_view.result.score > 0
    assert len(male_view.result.explanation.matched_important) == len(QUESTIONS)
