from typing import List

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from cwd / standard locations before reading env vars.
load_dotenv()


class Settings(BaseSettings):
    # Default local frontend origins (Next.js + Vite dev servers).
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    cors_allow_credentials: bool = False
    cors_allow_methods: List[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: List[str] = Field(default_factory=lambda: ["*"])

    # Comma-separated extra origins (e.g. https://your-app.ngrok-free.app). Env: CORS_EXTRA_ORIGINS
    cors_extra_origins: str = Field(default="")

    log_level: str = "INFO"

    @model_validator(mode="after")
    def _merge_cors_origins(self):
        raw = (self.cors_extra_origins or "").strip()
        if not raw:
            return self
        extra = [o.strip() for o in raw.split(",") if o.strip()]
        merged = list(dict.fromkeys([*self.cors_origins, *extra]))
        object.__setattr__(self, "cors_origins", merged)
        return self

    @model_validator(mode="after")
    def _default_jwt_secret_for_local_dev(self):
        if not (self.jwt_secret_key or "").strip():
            object.__setattr__(
                self,
                "jwt_secret_key",
                "dev-only-set-JWT_SECRET_KEY-in-production",
            )
        return self

    weaviate_url: str = Field(
        default="http://localhost:8080",
        description="Weaviate REST/gRPC base URL (env: WEAVIATE_URL)",
    )
    similarity_threshold: float = Field(
        default=0.5,
        description="Minimum similarity for filtered Weaviate search (env: SIMILARITY_THRESHOLD)",
    )
    memory_threshold: float = Field(
        default=0.85,
        description="Similarity threshold for strong Weaviate match; above hybrid floor, memory is merged with live APIs (env: MEMORY_THRESHOLD)",
    )
    hybrid_threshold: float = Field(
        default=0.5,
        description="Similarity floor for HYBRID strategy (env: HYBRID_THRESHOLD)",
    )
    model_name: str = Field(
        default="all-MiniLM-L6-v2",
        description="Sentence-transformers model id (env: MODEL_NAME)",
    )

    course_search_api_url: str = Field(
        default="",
        description="GET endpoint for external course search (query params: query, level, duration, goal, limit). Env: COURSE_SEARCH_API_URL",
    )
    course_search_api_key: str = Field(
        default="",
        description="Optional Bearer token for course search API (env: COURSE_SEARCH_API_KEY)",
    )
    course_search_timeout_seconds: float = Field(
        default=15.0,
        description="HTTP timeout for course search API (env: COURSE_SEARCH_TIMEOUT_SECONDS)",
    )

    users_db_path: str = Field(
        default="users.db",
        description="SQLite path for auth users (env: USERS_DB_PATH). Use an EBS path on EC2 for persistence.",
    )
    jwt_secret_key: str = Field(
        default="",
        description="HS256 signing secret for access tokens (env: JWT_SECRET_KEY). Required for multi-instance deploys.",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm (env: JWT_ALGORITHM)")
    jwt_expire_minutes: int = Field(
        default=10080,
        description="Access token lifetime in minutes (default 7 days; env: JWT_EXPIRE_MINUTES)",
    )
    auth_dev_fallback_email: bool = Field(
        default=False,
        description=(
            "If true, protected routes accept user identity via ?email=, X-Dev-User-Email header, "
            "or optional JSON `email` when Authorization Bearer is missing (local dev only). "
            "Env: AUTH_DEV_FALLBACK_EMAIL"
        ),
    )
    progress_daily_goal_minutes: int = Field(
        default=60,
        description="Daily learning-time goal in minutes for dashboard ratio (env: PROGRESS_DAILY_GOAL_MINUTES)",
    )
    progress_activity_chart_days: int = Field(
        default=14,
        ge=1,
        le=90,
        description="Days included in GET /progress activity series (env: PROGRESS_ACTIVITY_CHART_DAYS)",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
