from datetime import date

import pytest

from core.consent import CURRENT_CONSENT_VERSION
from core.models import Gender
from core.repository import (
    create_user,
    get_answered_question_keys,
    get_user_by_tg_id,
    renew_consent,
    save_answer,
)

pytestmark = pytest.mark.asyncio


async def make_user(session, tg_id: int = 111):
    return await create_user(
        session,
        tg_id=tg_id,
        name="Айгерим",
        gender=Gender.FEMALE,
        birth_date=date(1998, 3, 5),
        city="Астана",
        willing_to_relocate=False,
        consent_version=CURRENT_CONSENT_VERSION,
    )


async def test_create_and_get_user_by_tg_id(db_session):
    created = await make_user(db_session)

    found = await get_user_by_tg_id(db_session, created.tg_id)

    assert found is not None
    assert found.id == created.id
    assert found.name == "Айгерим"


async def test_get_user_by_tg_id_returns_none_for_unknown(db_session):
    found = await get_user_by_tg_id(db_session, 999999)

    assert found is None


async def test_renew_consent_updates_date_and_version(db_session):
    user = await make_user(db_session)
    old_date = user.consent_date

    await renew_consent(db_session, user, "2.0")

    assert user.consent_version == "2.0"
    assert user.consent_date >= old_date


async def test_save_answer_and_get_answered_keys(db_session):
    user = await make_user(db_session)

    await save_answer(
        db_session,
        user_id=user.id,
        question_key="smoking",
        own_option="does_not_smoke",
        acceptable_options=["does_not_smoke", "occasionally"],
        importance=2,
    )

    keys = await get_answered_question_keys(db_session, user.id)

    assert keys == {"smoking"}


async def test_save_answer_overwrites_existing_answer(db_session):
    user = await make_user(db_session)

    await save_answer(
        db_session,
        user_id=user.id,
        question_key="smoking",
        own_option="smokes",
        acceptable_options=["smokes"],
        importance=1,
    )
    await save_answer(
        db_session,
        user_id=user.id,
        question_key="smoking",
        own_option="does_not_smoke",
        acceptable_options=["does_not_smoke"],
        importance=2,
    )

    keys = await get_answered_question_keys(db_session, user.id)

    assert keys == {"smoking"}
