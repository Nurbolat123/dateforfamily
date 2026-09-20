import pytest
from pydantic import ValidationError

from core.config import Settings


def test_database_url_is_required(monkeypatch):
    # Регрессия: раньше при отсутствии .env тихо подставлялся пароль-заглушка
    # "postgres/postgres" — теперь программа должна сразу и явно упасть.
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
