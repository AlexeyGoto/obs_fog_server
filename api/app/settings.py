from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    database_url: str = 'sqlite:////data/db/app.db'

    app_base_url: str = 'http://127.0.0.1:8080'
    hls_base_url: str = 'http://nginx:8080/hls'

    jwt_secret: str = 'change_me'
    bot_api_token: str = 'change_me'

    telegram_bot_token: str = ''
    telegram_admin_id: str | None = None


settings = Settings()
