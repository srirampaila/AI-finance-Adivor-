import pytest
from pydantic import ValidationError
from app.core.config import Settings

def test_development_config_accepts_defaults():
    settings = Settings(APP_ENV="development")
    assert settings.DEBUG is True
    assert settings.JWT_SECRET == "development_secret_key_change_in_production_32chars_min"
    assert "localhost" in settings.DATABASE_URL

def test_production_config_rejects_default_jwt():
    with pytest.raises(ValueError, match="JWT_SECRET must be configured securely for production."):
        Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql+asyncpg://user:pass@prod-db.com/db",
            JWT_SECRET="development_secret_key_change_in_production_32chars_min"
        )

def test_production_config_rejects_localhost_db():
    with pytest.raises(ValueError, match="Production DATABASE_URL must not point to localhost."):
        Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/db",
            JWT_SECRET="super_secret_production_key_32_chars_long"
        )

def test_production_config_forces_debug_false():
    settings = Settings(
        APP_ENV="production",
        DATABASE_URL="postgresql+asyncpg://user:pass@prod-db.com/db",
        JWT_SECRET="super_secret_production_key_32_chars_long",
        DEBUG=True  # Attempt to force True
    )
    assert settings.DEBUG is False

def test_production_config_accepts_valid_settings():
    settings = Settings(
        APP_ENV="production",
        DATABASE_URL="postgresql+asyncpg://user:pass@prod-db.com/db",
        JWT_SECRET="super_secret_production_key_32_chars_long"
    )
    assert settings.APP_ENV == "production"
    assert settings.DEBUG is False
    assert settings.JWT_SECRET == "super_secret_production_key_32_chars_long"
    assert "prod-db.com" in settings.DATABASE_URL


def test_database_url_normalization_postgres_schemes_and_ssl():
    """Verify that normalize_database_url correctly handles schemes, sslmode translation, and parameter preservation."""
    # 1. Standard postgresql:// with sslmode=require
    url1 = "postgresql://neondb_owner:pass@ep-xyz.singapore.aws.neon.tech/neondb?sslmode=require"
    assert Settings.normalize_database_url(url1) == "postgresql+asyncpg://neondb_owner:pass@ep-xyz.singapore.aws.neon.tech/neondb?ssl=require"

    # 2. Standard postgres:// with sslmode=require
    url2 = "postgres://neondb_owner:pass@ep-xyz.singapore.aws.neon.tech:5432/neondb?sslmode=require"
    assert Settings.normalize_database_url(url2) == "postgresql+asyncpg://neondb_owner:pass@ep-xyz.singapore.aws.neon.tech:5432/neondb?ssl=require"

    # 3. Already postgresql+asyncpg:// with sslmode=require
    url3 = "postgresql+asyncpg://user:pass@localhost:5432/db?sslmode=require"
    assert Settings.normalize_database_url(url3) == "postgresql+asyncpg://user:pass@localhost:5432/db?ssl=require"

    # 4. Preserving other query parameters
    url4 = "postgresql://user:pass@host/db?sslmode=require&application_name=ai_finance&connect_timeout=10"
    norm4 = Settings.normalize_database_url(url4)
    assert norm4.startswith("postgresql+asyncpg://")
    assert "ssl=require" in norm4
    assert "sslmode" not in norm4
    assert "application_name=ai_finance" in norm4
    assert "connect_timeout=10" in norm4

    # 5. URLs without SSL parameters
    url5 = "postgresql://user:pass@host:5432/db"
    assert Settings.normalize_database_url(url5) == "postgresql+asyncpg://user:pass@host:5432/db"

    # 6. Encoded special characters in password are preserved
    url6 = "postgresql://user:p%40ss%3Aword%231@ep-xyz.neon.tech:5432/neondb?sslmode=require"
    norm6 = Settings.normalize_database_url(url6)
    assert "user:p%40ss%3Aword%231@ep-xyz.neon.tech:5432" in norm6
    assert "ssl=require" in norm6

    # 7. Already ssl=require (does not duplicate)
    url7 = "postgresql://user:pass@host/db?ssl=require"
    assert Settings.normalize_database_url(url7) == "postgresql+asyncpg://user:pass@host/db?ssl=require"

    # 8. SQLite URLs preserved
    assert Settings.normalize_database_url("sqlite:///./test.db") == "sqlite+aiosqlite:///./test.db"
    assert Settings.normalize_database_url("sqlite+aiosqlite:///./test.db") == "sqlite+aiosqlite:///./test.db"

