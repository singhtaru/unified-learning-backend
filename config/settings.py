from typing import List

from dotenv import load_dotenv
from pydantic import Field
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

    log_level: str = "INFO"

    weaviate_url: str = Field(
        default="http://localhost:8080",
        description="Weaviate REST/gRPC base URL (env: WEAVIATE_URL)",
    )
    similarity_threshold: float = Field(
        default=0.5,
        description="Minimum similarity for filtered Weaviate search (env: SIMILARITY_THRESHOLD)",
    )
    memory_threshold: float = Field(
        default=0.7,
        description="Similarity threshold for MEMORY strategy (env: MEMORY_THRESHOLD)",
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
