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

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
DEFAULT_JWT_ALGORITHMS = ["ES256", "RS256"]
#: Image-text providers ``VISION_PROVIDER_ORDER`` may name, in order.
KNOWN_VISION_PROVIDERS = ("groq", "rapidocr")


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
    #: Single source of truth for the local dev server bind address. Read by the
    #: dev scripts, the Vite proxy and any local run command. ``HOST``/``PORT``
    #: are accepted as deprecated aliases so older .env files keep working.
    backend_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("BACKEND_HOST", "HOST"),
    )
    backend_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("BACKEND_PORT", "PORT"),
    )
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
    #: Dedicated extraction LLM (separate key + model) for structured memory and
    #: activity extraction only. Optional: when ``GROQ_EXTRACTION_API_KEY`` is
    #: unset the extractor is disabled and chat is completely unaffected. It
    #: never answers to the user or replaces the primary Groq agent.
    extraction_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GROQ_EXTRACTION_API_KEY", "EXTRACTION_API_KEY"),
    )
    extraction_model: str = Field(
        default="openai/gpt-oss-20b",
        validation_alias=AliasChoices("GROQ_EXTRACTION_MODEL", "EXTRACTION_MODEL"),
    )
    #: Vision-capable Groq model id. Leave unset to auto-detect from the
    #: account's model list. ``GROQ_VISION_MODEL`` stays accepted as an alias.
    vision_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VISION_MODEL", "GROQ_VISION_MODEL"),
    )
    #: Ordered image-text providers. Supported: groq, rapidocr. The first
    #: provider that returns text wins; local OCR needs no API key.
    vision_provider_order: Annotated[list[str], NoDecode] = ["groq", "rapidocr"]
    #: Longest image edge (px) used for OCR after downscaling.
    ocr_max_side_px: int = 1600
    chromadb_persist_dir: str = "./chroma_data"
    chromadb_collection_name: str = "fitai_knowledge"
    embedding_model: str = "all-MiniLM-L6-v2"

    # Agent feature flags (additive, default OFF until verified)
    agent_web_tools: bool = False
    agent_location_tools: bool = False
    agent_multi_agent: bool = False
    #: Enable the dedicated activity/memory extractor in the chat flow. Even when
    #: True, the extractor no-ops (and chat proceeds normally) if no
    #: ``GROQ_EXTRACTION_API_KEY`` is configured.
    agent_activity_extraction: bool = True

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

    @field_validator("vision_provider_order", mode="before")
    @classmethod
    def _split_vision_providers(cls, value: object) -> object:
        if isinstance(value, str):
            parts = [item.strip().lower() for item in value.split(",") if item.strip()]
            if not parts:
                return []
            unknown = [item for item in parts if item not in KNOWN_VISION_PROVIDERS]
            if unknown:
                raise ValueError(
                    f"unknown VISION_PROVIDER_ORDER entries {unknown}; "
                    f"expected any of {list(KNOWN_VISION_PROVIDERS)}"
                )
            return parts
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
    def extraction_enabled(self) -> bool:
        """True when the dedicated activity extractor should run.

        Requires the flag to be on AND a dedicated key to be present, so a
        missing key disables extraction without breaking chat.
        """
        return self.agent_activity_extraction and bool(self.extraction_api_key)

    @property
    def vision_providers(self) -> list[str]:
        """Ordered image-text providers; an empty setting means "all known"."""
        return self.vision_provider_order or list(KNOWN_VISION_PROVIDERS)

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
