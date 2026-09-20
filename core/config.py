from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки проекта, загружаются из .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    # Без значения по умолчанию: если .env потерян или не заполнен, программа
    # должна сразу и громко упасть с понятной ошибкой, а не тихо подключиться
    # к чужой или тестовой базе со слабым паролем "postgres/postgres".
    database_url: str
    admin_username: str = "admin"
    admin_password: str = ""


settings = Settings()
