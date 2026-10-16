from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env lives in backend/ (local dev); on Vercel these come from project env vars.
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    frontend_origin: str = "http://localhost:3000"
    # Supabase pooled Postgres URL (port 6543). Falls back to local SQLite.
    database_url: str = "sqlite:///banyan.db"

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    # Free alternative: Google AI Studio via its OpenAI-compatible endpoint.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    mock_llm: bool = False  # force the scripted offline LLM (also used when no OpenAI key)
    max_parallel_agents: int = 5
    max_depth: int = 3
    branch_token_budget: int = 40000
    confidence_threshold: float = 0.6
    sandbox_timeout_sec: float = 20
    vault_key: str = ""  # encrypts the secrets vault; set it in production
    watch_interval_sec: int = 15  # minimum gap between two checks of one watcher
    cron_secret: str = ""  # required by /api/watches/tick_all (Vercel cron / GitHub Actions)
    elevenlabs_api_key: str = ""  # optional: natural agent voices; without it the browser speaks
    elevenlabs_voice_orchestrator: str = ""
    elevenlabs_voice_builder: str = ""
    elevenlabs_voice_critic: str = ""
    elevenlabs_voice_watcher: str = ""

    @property
    def provider(self) -> str:
        return "openai" if self.openai_api_key else "gemini" if self.gemini_api_key else "mock"

    @property
    def llm_model(self) -> str:
        return self.openai_model if self.provider == "openai" else self.gemini_model

    @property
    def use_mock(self) -> bool:
        return self.mock_llm or self.provider == "mock"

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
