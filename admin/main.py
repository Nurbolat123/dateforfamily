"""Админка: простой веб-интерфейс для проверки анкет, подборок и жалоб.

Запуск (после активации виртуального окружения):
    uvicorn admin.main:app --reload

Открывается в браузере по адресу http://127.0.0.1:8000 — попросит логин и
пароль из .env (ADMIN_USERNAME / ADMIN_PASSWORD).
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import require_admin, require_same_origin
from core.config import settings
from core.db import get_session
from core.format import calculate_age
from core.models import Gender, MatchStatus, UserStatus
from core.questions import QUESTIONS
from core.repository import (
    get_answered_question_keys,
    get_report_by_id,
    get_user_by_id,
    list_all_matches,
    list_all_reports,
    list_all_users,
    resolve_report,
    set_user_status,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.admin_password:
        raise RuntimeError(
            "ADMIN_PASSWORD не задан. Впишите пароль в .env перед запуском админки — "
            "без него никто не сможет (и, для безопасности, не должен) в неё войти."
        )
    yield


app = FastAPI(title="Админка сервиса знакомств", lifespan=lifespan)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

GENDER_LABELS = {Gender.MALE: "Мужской", Gender.FEMALE: "Женский"}
USER_STATUS_LABELS = {
    UserStatus.NEW: "Новый",
    UserStatus.VERIFIED: "Подтверждён",
    UserStatus.BLOCKED: "Заблокирован",
}
MATCH_STATUS_LABELS = {
    MatchStatus.PENDING: "Ожидает",
    MatchStatus.INTERESTED: "Интересно",
    MatchStatus.DECLINED: "Не интересно",
}


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse("/users")


@app.get("/users")
async def users_page(
    request: Request,
    admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    all_users = await list_all_users(session)
    rows = []
    for user in all_users:
        answered = await get_answered_question_keys(session, user.id)
        rows.append(
            {
                "id": user.id,
                "name": user.name,
                "gender_label": GENDER_LABELS.get(user.gender, user.gender.value),
                "age": calculate_age(user.birth_date),
                "city": user.city,
                "answered_count": len(answered),
                "total_questions": len(QUESTIONS),
                "status": user.status,
                "status_label": USER_STATUS_LABELS.get(user.status, user.status.value),
            }
        )
    return templates.TemplateResponse(
        request, "users.html", {"users": rows, "active": "users"}
    )


@app.post("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    status: str = Form(...),
    admin: str = Depends(require_admin),
    _origin: None = Depends(require_same_origin),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    try:
        new_status = UserStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Неизвестный статус: {status}")

    user = await get_user_by_id(session, user_id)
    if user is not None:
        await set_user_status(session, user, new_status)
    return RedirectResponse("/users", status_code=303)


@app.get("/matches")
async def matches_page(
    request: Request,
    admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    all_matches = await list_all_matches(session)
    rows = []
    for match in all_matches:
        user_a = await get_user_by_id(session, match.user_a_id)
        user_b = await get_user_by_id(session, match.user_b_id)
        rows.append(
            {
                "week": match.week.isoformat(),
                "user_a_name": user_a.name if user_a else "?",
                "user_b_name": user_b.name if user_b else "?",
                "percent": round(match.score * 100),
                "status_a_label": MATCH_STATUS_LABELS.get(match.status_a, match.status_a.value),
                "status_b_label": MATCH_STATUS_LABELS.get(match.status_b, match.status_b.value),
                "created_at": match.created_at.strftime("%d.%m.%Y %H:%M"),
            }
        )
    return templates.TemplateResponse(
        request, "matches.html", {"matches": rows, "active": "matches"}
    )


@app.get("/reports")
async def reports_page(
    request: Request,
    admin: str = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    all_reports = await list_all_reports(session)
    rows = []
    for report in all_reports:
        from_user = await get_user_by_id(session, report.from_user_id)
        on_user = await get_user_by_id(session, report.on_user_id)
        rows.append(
            {
                "id": report.id,
                "from_user_name": from_user.name if from_user else "?",
                "on_user_name": on_user.name if on_user else "?",
                "reason": report.reason,
                "resolved": report.resolved,
            }
        )
    return templates.TemplateResponse(
        request, "reports.html", {"reports": rows, "active": "reports"}
    )


@app.post("/reports/{report_id}/resolve")
async def resolve_report_view(
    report_id: int,
    admin: str = Depends(require_admin),
    _origin: None = Depends(require_same_origin),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    report = await get_report_by_id(session, report_id)
    if report is not None:
        await resolve_report(session, report)
    return RedirectResponse("/reports", status_code=303)
