"""Application configuration.

Settings are loaded from environment variables (and an optional local `.env`
file) through pydantic-settings. Every value has a safe, non-secret default so
that modules can be imported and developed before production credentials exist.
Real secrets must be supplied through the environment, never committed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
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

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
DEFAULT_JWT_ALGORITHMS = ["ES256", "RS256"]
#: Image-text providers ``VISION_PROVIDER_ORDER`` may name, in order.
KNOWN_VISION_PROVIDERS = ("groq", "rapidocr")


#: ``backend/``: the anchor for every relative persistent path.
BACKEND_DIR = Path(__file__).resolve().parents[2]


def resolve_storage_path(value: str | Path) -> Path:
    """Return an absolute path; relative values are anchored to ``backend/``.

    ``~`` is expanded. The result never depends on the process working directory.
    """
    path = Path(value).expanduser()
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


class Settings(BaseSettings):
    """Runtime configuration for the FitAI backend."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "FitAI Backend"
    #: Which deployable service this process is: ``core`` | ``documents``.
    #: Only used to scope production start-up validation to what the service needs.
    service_name: str = Field(
        default="core", validation_alias=AliasChoices("FITAI_SERVICE", "SERVICE_NAME")
    )
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
    #: Optional regex of additionally allowed origins (e.g. Vercel preview URLs:
    #: ``https://fitai-.*-myteam\.vercel\.app``). Empty means exact origins only.
    cors_origin_regex: str | None = None

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
    #: unconfigured | local | supabase
    document_storage_backend: str = "unconfigured"
    #: Private Supabase Storage bucket for the original uploads.
    supabase_storage_bucket: str = "fitai-documents"
    supabase_storage_timeout_s: float = 30.0

    # Whether the Core API serves the document routes. Defaults to True so a local
    # single-process run (and the existing test-suite) keeps working; the
    # production Core image sets it to false and the dedicated Documents service
    # owns those routes.
    serve_documents_routes: bool = True

    #: Directory holding the built frontend (``index.html`` + ``assets/``). When it
    #: exists, Core serves the single-page app itself (one-service deployment).
    #: Unset (the default) keeps Core API-only.
    frontend_dist_dir: str | None = None

    # Vector storage: ``chroma`` (local, development default) or ``pgvector``
    # (Supabase PostgreSQL, production).
    vector_store_backend: str = "chroma"
    #: Embeddings: ``local`` (Chroma's bundled ONNX MiniLM) or ``remote`` (HTTP).
    embedding_provider: str = "local"
    #: Feature-extraction endpoint for ``remote`` (no default: must be configured).
    embedding_api_url: str | None = None
    embedding_api_key: str | None = None
    #: Model name sent to ``openai``-format endpoints (``hf`` endpoints embed it in the URL).
    embedding_remote_model: str | None = None
    #: ``hf`` (HuggingFace feature-extraction) or ``openai`` (/embeddings).
    embedding_api_format: str = "hf"
    #: Dimension every vector must have; all-MiniLM-L6-v2 produces 384.
    embedding_dimension: int = 384
    embedding_batch_size: int = 32
    embedding_timeout_s: float = 30.0

    # Document ingestion. ``inline`` keeps the original in-process BackgroundTask
    # (development / tests). ``jobs`` persists a job row per document and
    # processes it in checkpointed batches so a restart resumes instead of failing.
    ingestion_mode: str = "inline"
    ingestion_worker_enabled: bool = True
    ingestion_pages_per_batch: int = 5
    ingestion_poll_seconds: float = 5.0
    ingestion_lease_seconds: int = 120
    ingestion_max_attempts: int = 3

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
    #: Hard cap on one extraction call. Extraction runs inline, before the reply,
    #: so a slow or hanging provider must not hold the user's response open
    #: indefinitely. On timeout extraction is skipped for that turn (chat
    #: continues, nothing is claimed as saved) and the next message retries.
    extraction_timeout_s: float = 20.0

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

    # Guardrails configuration
    guardrails_enabled: bool = True
    guardrails_mode: str = "enforce"  # "enforce" | "monitor" | "disabled"
    guard_model: str | None = None  # model for LLM classifier (defaults to groq_model)
    #: Prompt-injection guard model (``meta-llama/llama-prompt-guard-2-86m``).
    #: It scores untrusted text (user messages and retrieved documents) safe or
    #: unsafe and never answers the user. Optional: when unset or disabled the
    #: deterministic safety rules remain the only gate and chat is unaffected.
    prompt_guard_enabled: bool = True
    prompt_guard_model: str = Field(
        default="meta-llama/llama-prompt-guard-2-86m",
        validation_alias=AliasChoices("PROMPT_GUARD_MODEL", "GUARD_MODEL"),
    )
    #: Key for the guard model. Empty means "reuse the primary Groq key".
    prompt_guard_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("PROMPT_GUARD_API_KEY", "GUARD_API_KEY")
    )
    #: Score at or above which text is treated as a prompt-injection attempt.
    prompt_guard_threshold: float = 0.5
    #: Hard timeout for one screening call; on error the guard fails open.
    prompt_guard_timeout_s: float = 2.0
    guard_canary: str | None = None  # canary token for output guard
    #: Run the LLM intent classifier as the decision layer on top of the
    #: deterministic rules. Disable to fall back to deterministic-only gating.
    guard_classifier_enabled: bool = True
    #: Per-call timeout (seconds) for the classifier's single Groq completion.
    guard_timeout_s: float = 1.5
    #: Cap on the classifier's completion length; its JSON verdict is tiny.
    guard_max_tokens: int = 200
    #: Below this classifier confidence the decision degrades to the
    #: deterministic fallback (allow + no cache), i.e. fail-open to current
    #: behaviour rather than block on a weak signal.
    guard_conf_threshold: float = 0.6

    # Cross-chat continuity (memories + past-chat summaries)
    #: Master switch for continuity recall and summary indexing.
    continuity_enabled: bool = True
    #: Dedicated model for conversation summaries (defaults to the main model).
    summary_model: str | None = None
    #: Default for the per-user "reference past chats" toggle (server-enforced).
    past_chat_recall_default: bool = True
    #: Default for the per-user "use memory" toggle (server-enforced).
    memory_recall_default: bool = True
    #: Number of recalled items requested from the continuity store per layer.
    continuity_recall_k: int = 4

    # Location / weather defaults
    geocoding_provider: str = "nominatim"  # nominatim | google | mapbox
    google_geocoding_api_key: str | None = None
    mapbox_api_key: str | None = None
    places_provider: str = "overpass"  # overpass | google | foursquare
    google_places_api_key: str | None = None
    foursquare_api_key: str | None = None
    weather_provider: str = "open-meteo"  # open-meteo only for now

    @field_validator("upload_dir", "chromadb_persist_dir")
    @classmethod
    def _anchor_storage_dir(cls, value: str) -> str:
        """Resolve relative storage directories against ``backend/``.

        Without this, uploads and the Chroma store would be created relative to
        wherever the process was launched, silently forking user data.
        Absolute paths (e.g. a Docker volume mount) are used as given.
        """
        return str(resolve_storage_path(value))

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalise_postgres_scheme(cls, value: object) -> object:
        """Accept the ``postgres://`` / ``postgresql://`` URLs hosting providers hand out.

        SQLAlchemy 2 rejects ``postgres://`` and would pick whichever default
        driver is installed for ``postgresql://``; this project ships psycopg2.
        """
        if isinstance(value, str):
            value = value.strip()
            for prefix in ("postgres://", "postgresql://"):
                if value.startswith(prefix):
                    return "postgresql+psycopg2://" + value[len(prefix) :]
        return value

    @field_validator("database_url")
    @classmethod
    def _anchor_sqlite_path(cls, value: str) -> str:
        """Resolve relative SQLite file paths against ``backend/``.

        Otherwise the app, Alembic and scripts would open different files depending
        on the process working directory.
        """
        from sqlalchemy.engine import make_url

        url = make_url(value)
        if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
            return value
        path = Path(url.database)
        if path.is_absolute():
            return value
        return url.set(database=(BACKEND_DIR / path).as_posix()).render_as_string(
            hide_password=False
        )

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

    def production_problems(self) -> list[str]:
        """Configuration mistakes that must never reach a production start.

        Checks are scoped by ``service_name`` so the Documents service is not forced
        to carry a Groq key.
        """
        service = self.service_name.strip().lower()
        problems: list[str] = []
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must be a PostgreSQL URL, not SQLite.")
        origins = self.cors_origins
        if "*" in origins:
            problems.append("CORS_ORIGINS must list explicit origins, not '*'.")
        elif not any("localhost" not in o and "127.0.0.1" not in o for o in origins):
            problems.append("CORS_ORIGINS must include the deployed frontend origin.")
        elif any(not o.startswith("https://") and "localhost" not in o for o in origins):
            problems.append("CORS_ORIGINS must use https:// for non-local origins.")
        if not self.supabase_url:
            problems.append("SUPABASE_URL is required to verify sign-in tokens.")
        if self.debug:
            problems.append("DEBUG must be false.")

        if service == "core" and not self.groq_api_key:
            problems.append("GROQ_API_KEY is required for chat.")

        serves_documents = service == "documents" or (
            service == "core" and self.serve_documents_routes
        )
        if serves_documents:
            backend = self.document_storage_backend.strip().lower()
            if backend not in {"local", "supabase"}:
                problems.append(
                    "DOCUMENT_STORAGE_BACKEND must be 'supabase' (or 'local' with "
                    "UPLOAD_DIR on a persistent disk); other values leave uploads disabled."
                )
            if backend == "supabase" and not self.supabase_service_role_key:
                problems.append("SUPABASE_SERVICE_ROLE_KEY is required for Supabase Storage.")

        uses_vectors = service in {"core", "documents"}
        if uses_vectors and self.vector_store_backend.strip().lower() == "pgvector":
            problems.extend(self._remote_embedding_problems())
        if service == "documents" and self.vector_store_backend.strip().lower() != "pgvector":
            problems.append("VECTOR_STORE_BACKEND must be 'pgvector' for the documents service.")
        if service == "documents" and self.ingestion_mode.strip().lower() != "jobs":
            problems.append("INGESTION_MODE must be 'jobs' for the documents service.")

        return problems

    def _remote_embedding_problems(self) -> list[str]:
        """pgvector deployments must embed through a remote provider."""
        problems: list[str] = []
        if self.embedding_provider.strip().lower() != "remote":
            problems.append(
                "EMBEDDING_PROVIDER must be 'remote' with VECTOR_STORE_BACKEND=pgvector: "
                "a local embedding model does not fit a 512 MB instance."
            )
        elif not self.embedding_api_url or not self.embedding_api_key:
            problems.append("EMBEDDING_API_URL and EMBEDDING_API_KEY are required.")
        return problems

    @model_validator(mode="after")
    def _reject_unsafe_production(self) -> Settings:
        if self.is_production:
            problems = self.production_problems()
            if problems:
                bullets = "".join(f"\n- {p}" for p in problems)
                raise ValueError("Invalid production configuration:" + bullets)
        return self

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
