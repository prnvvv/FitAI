"""Application configuration.

Settings are loaded from environment variables (and an optional local `.env`
file) through pydantic-settings. Every value has a safe, non-secret default so
that modules can be imported and developed before production credentials exist.
Real secrets must be supplied through the environment, never committed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

# Work around langchain<->langchain-core version mismatch: langchain_core expects
# ``langchain.debug`` but langchain 1.x no longer exposes it. Defining it here
# prevents AttributeError inside LangGraph/LangChain callback configuration.
try:
    import langchain

    if not hasattr(langchain, "debug"):
        langchain.debug = False
except Exception:
    pass

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
DEFAULT_JWT_ALGORITHMS = ["ES256", "RS256"]


class Settings(BaseSettings):
    """Runtime configuration for the FitAI backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "FitAI Backend"
    environment: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    cors_origins: Annotated[list[str], NoDecode] = DEFAULT_CORS_ORIGINS

    # Database
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/fitai"
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle_seconds: int = 1800
    db_echo: bool = False

    # Supabase Auth
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_jwt_secret: str | None = None
    supabase_jwt_algorithms: Annotated[list[str], NoDecode] = DEFAULT_JWT_ALGORITHMS
    supabase_jwt_audience: str | None = "authenticated"
    supabase_jwks_cache_seconds: int = 3600

    # File uploads / document storage
    max_upload_size_mb: int = 10
    upload_dir: str = "./uploads"
    document_storage_backend: str = "unconfigured"

    # AI / retrieval configuration is owned by Person 2. These values are kept
    # here only so both developers share a single configuration source.
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    chromadb_persist_dir: str = "./chroma_data"
    chromadb_collection_name: str = "fitai_knowledge"
    embedding_model: str = "all-MiniLM-L6-v2"

    # Agent feature flags (additive, default OFF until verified)
    agent_web_tools: bool = False
    agent_location_tools: bool = False
    agent_multi_agent: bool = False

    # Web search provider chain (comma-separated priority list).
    # Supported: tavily, brave, serper, ddgs. Missing/empty defaults to "ddgs".
    search_providers: Annotated[list[str], NoDecode] = ["ddgs"]
    tavily_api_key: str | None = None
    brave_api_key: str | None = None
    serper_api_key: str | None = None

    # Web fetch / research budgets
    web_fetch_timeout_seconds: float = 12.0
    web_max_redirects: int = 3
    web_max_content_bytes: int = 2_000_000
    web_max_tool_calls_per_turn: int = 6
    web_cache_ttl_seconds: int = 300
    web_user_rate_limit_per_minute: int = 30

    # Multi-agent model roles (defaults to the main Groq model)
    router_model: str | None = None
    research_model: str | None = None
    synth_model: str | None = None

    # Location / weather defaults
    geocoding_provider: str = "nominatim"  # nominatim | google | mapbox
    google_geocoding_api_key: str | None = None
    mapbox_api_key: str | None = None
    places_provider: str = "overpass"  # overpass | google | foursquare
    google_places_api_key: str | None = None
    foursquare_api_key: str | None = None
    weather_provider: str = "open-meteo"  # open-meteo only for now

    @field_validator("search_providers", mode="before")
    @classmethod
    def _split_providers(cls, value: object) -> object:
        if isinstance(value, str):
            parts = [item.strip().lower() for item in value.split(",") if item.strip()]
            return parts if parts else ["ddgs"]
        return value

    @field_validator("cors_origins", "supabase_jwt_algorithms", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        """Allow comma-separated strings for list settings in environment files."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        """Return True when running outside local development."""
        return self.environment.lower() in {"production", "prod"}

    @property
    def jwks_url(self) -> str | None:
        """Return the Supabase JWKS endpoint when a project URL is configured."""
        if not self.supabase_url:
            return None
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def jwt_issuer(self) -> str | None:
        """Return the expected token issuer when a project URL is configured."""
        if not self.supabase_url:
            return None
        return f"{self.supabase_url.rstrip('/')}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
