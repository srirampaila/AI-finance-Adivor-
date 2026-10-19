from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json
import urllib.parse


class Settings(BaseSettings):
    """Centralized environment settings for AI Finance Advisor."""

    APP_NAME: str = "AI Finance Advisor"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # CORS configuration
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Database & Security configuration
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_finance_db"
    JWT_SECRET: str = "development_secret_key_change_in_production_32chars_min"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # AI & LLM Advisor configuration
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: Optional[str] = None
    AI_PROVIDER: str = "openai"  # "openai" | "deterministic"
    AI_TIMEOUT_SECONDS: float = 15.0
    AI_RATE_LIMIT_PER_MINUTE: int = 30

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if not v:
            return v

        # 1. Handle SQLite async prefix
        if v.startswith("sqlite://") and not v.startswith("sqlite+aiosqlite://"):
            return v.replace("sqlite://", "sqlite+aiosqlite://", 1)
        if v.startswith("sqlite+aiosqlite://"):
            return v

        # 2. Handle PostgreSQL schemes and asyncpg query parameters
        parts = urllib.parse.urlsplit(v)
        scheme = parts.scheme

        if scheme in ("postgres", "postgresql", "postgresql+asyncpg"):
            scheme = "postgresql+asyncpg"
            query = parts.query
            if query:
                params = urllib.parse.parse_qsl(query, keep_blank_values=True)
                new_params = []
                has_ssl = any(k == "ssl" for k, _ in params)
                for k, val in params:
                    if k == "sslmode":
                        # asyncpg does not accept 'sslmode' connection argument; translate to 'ssl'
                        if not has_ssl:
                            new_params.append(("ssl", val))
                            has_ssl = True
                    else:
                        new_params.append((k, val))
                query = urllib.parse.urlencode(new_params)
            return urllib.parse.urlunsplit((scheme, parts.netloc, parts.path, query, parts.fragment))

        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.APP_ENV == "production":
            self.DEBUG = False
            if self.JWT_SECRET == "development_secret_key_change_in_production_32chars_min":
                raise ValueError("JWT_SECRET must be configured securely for production.")
            if "localhost" in self.DATABASE_URL or "127.0.0.1" in self.DATABASE_URL:
                raise ValueError("Production DATABASE_URL must not point to localhost.")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
