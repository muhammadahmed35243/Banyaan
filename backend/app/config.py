from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env lives in backend/ (local dev); on Vercel these come from project env vars.
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    frontend_origin: str = "http://localhost:3000"
    # Supabase pooled Postgres URL (port 6543). Falls back to local SQLite.
    database_url: str = "sqlite:///banyan.db"

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    mock_llm: bool = False  # force the scripted offline LLM (also used when no OpenAI key)
    max_parallel_agents: int = 5
    max_depth: int = 3
    branch_token_budget: int = 40000
    confidence_threshold: float = 0.6

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


settings = Settings()


# Tools read raw env vars (e.g. SERPAPI_API_KEY); make local .env values visible to them.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
