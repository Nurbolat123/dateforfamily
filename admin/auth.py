import secrets
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from core.config import settings

security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    # Пустой пароль никогда не считается верным — иначе при незаполненном
    # ADMIN_PASSWORD в .env админка была бы открыта для всех без пароля.
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пароль администратора не настроен (ADMIN_PASSWORD в .env)",
            headers={"WWW-Authenticate": "Basic"},
        )

    correct_username = secrets.compare_digest(credentials.username, settings.admin_username)
    correct_password = secrets.compare_digest(credentials.password, settings.admin_password)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


def require_same_origin(request: Request) -> None:
    """Простая защита от CSRF для форм админки.

    Вход по логину/паролю (HTTP Basic) не использует cookie, поэтому браузер
    сам повторно прикладывает сохранённые данные для входа к любому запросу
    на этот адрес — в том числе к тем, что незаметно отправила бы сторонняя
    вредоносная страница. Проверяем, что запрос действительно пришёл со
    страницы самой админки, а не откуда-то ещё.
    """
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Отсутствует заголовок Origin/Referer")

    source_host = urlparse(source).hostname
    if source_host != request.url.hostname:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недопустимый источник запроса")
