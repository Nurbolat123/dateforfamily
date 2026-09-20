"""Проверяет админку: вход по паролю, списки анкет/подборок/жалоб, кнопки."""

from datetime import date

import httpx
import pytest
from httpx import ASGITransport

from admin.main import app
from core.config import settings
from core.consent import CURRENT_CONSENT_VERSION
from core.models import Gender, UserStatus
from core.questions import QUESTIONS
from core.repository import create_report, create_user, save_answer
from core.weekly_matching import run_weekly_matching

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _set_admin_password(monkeypatch):
    # Задаём пароль явно, чтобы тест не зависел от содержимого локального .env.
    monkeypatch.setattr(settings, "admin_password", "test-admin-password")


async def make_client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    auth = (settings.admin_username, settings.admin_password)
    # Origin должен совпадать с base_url — иначе защита от CSRF (см.
    # admin/auth.py require_same_origin) отклонит POST-запросы, как и должна.
    return httpx.AsyncClient(
        transport=transport, base_url="http://test", auth=auth, headers={"origin": "http://test"}
    )


async def make_user(session, tg_id: int, gender: Gender, name: str, status=UserStatus.NEW):
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
    user.status = status
    await session.commit()
    return user


async def complete_survey(session, user_id: int) -> None:
    for question in QUESTIONS:
        own_value = question.options[0]
        await save_answer(
            session,
            user_id=user_id,
            question_key=question.key,
            own_option=own_value,
            acceptable_options=[own_value],
            importance=2,
        )


async def test_pages_require_authentication(db_session):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/users")
    assert response.status_code == 401


async def test_empty_admin_password_never_authenticates(db_session, monkeypatch):
    # Регрессия: пустой ADMIN_PASSWORD раньше означал "пароль не нужен".
    monkeypatch.setattr(settings, "admin_password", "")
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", auth=("admin", "")) as client:
        response = await client.get("/users")
    assert response.status_code == 401


async def test_post_without_matching_origin_is_rejected(db_session):
    # Регрессия: раньше формы можно было отправить с любого сайта (CSRF).
    user = await make_user(db_session, 1099, Gender.MALE, "Чужой")
    transport = ASGITransport(app=app)
    auth = (settings.admin_username, settings.admin_password)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", auth=auth) as client:
        response = await client.post(
            f"/users/{user.id}/status",
            data={"status": "blocked"},
            headers={"origin": "http://evil.example"},
        )

    assert response.status_code == 403
    await db_session.refresh(user)
    assert user.status == UserStatus.NEW  # запрос отклонён, статус не изменился


async def test_users_page_lists_registered_people(db_session):
    await make_user(db_session, 1001, Gender.MALE, "Данияр")

    async with await make_client() as client:
        response = await client.get("/users")

    assert response.status_code == 200
    assert "Данияр" in response.text
    assert "0 / 15" in response.text  # анкета не начата


async def test_verify_button_updates_status(db_session):
    user = await make_user(db_session, 1002, Gender.MALE, "Ержан")

    async with await make_client() as client:
        response = await client.post(f"/users/{user.id}/status", data={"status": "verified"})

    assert response.status_code in (200, 303)
    await db_session.refresh(user)
    assert user.status == UserStatus.VERIFIED


async def test_block_button_updates_status(db_session):
    user = await make_user(db_session, 1003, Gender.FEMALE, "Динара", status=UserStatus.VERIFIED)

    async with await make_client() as client:
        await client.post(f"/users/{user.id}/status", data={"status": "blocked"})

    await db_session.refresh(user)
    assert user.status == UserStatus.BLOCKED


async def test_matches_page_shows_pair_and_is_read_only(db_session):
    male = await make_user(db_session, 1004, Gender.MALE, "Аслан", status=UserStatus.VERIFIED)
    female = await make_user(db_session, 1005, Gender.FEMALE, "Гульнара", status=UserStatus.VERIFIED)
    await complete_survey(db_session, male.id)
    await complete_survey(db_session, female.id)
    await run_weekly_matching(db_session)

    async with await make_client() as client:
        response = await client.get("/matches")

    assert response.status_code == 200
    assert "Аслан" in response.text
    assert "Гульнара" in response.text
    assert "100%" in response.text
    assert "<form" not in response.text  # только просмотр, без кнопок действий


async def test_reports_page_and_resolve_button(db_session):
    reporter = await make_user(db_session, 1006, Gender.MALE, "Тимур")
    reported = await make_user(db_session, 1007, Gender.FEMALE, "Сауле")
    report = await create_report(
        db_session, from_user_id=reporter.id, on_user_id=reported.id, reason="Странное поведение"
    )

    async with await make_client() as client:
        list_response = await client.get("/reports")
        assert "Странное поведение" in list_response.text
        assert "Открыта" in list_response.text

        await client.post(f"/reports/{report.id}/resolve")
        after_response = await client.get("/reports")

    assert "Решено" in after_response.text
