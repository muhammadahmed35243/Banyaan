from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env lives in backend/ (local dev); on Vercel these come from project env vars.
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    frontend_origin: str = "http://localhost:3000"
    # Supabase pooled Postgres URL (port 6543). Falls back to local SQLite.
    database_url: str = "sqlite:///banyan.db"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


settings = Settings()
