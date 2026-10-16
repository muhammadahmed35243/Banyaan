from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env lives at the repo root, one level above backend/
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    frontend_origin: str = "http://localhost:3000"
    database_url: str = "sqlite:///banyan.db"


settings = Settings()
