"""Tests for Alembic migration upgrade and downgrade."""

import os
from alembic import command
from alembic.config import Config
import pytest


def test_alembic_migrations_upgrade_and_downgrade(tmp_path):
    """Verify that Alembic migrations run cleanly up and down on an isolated database."""
    test_db_file = tmp_path / "migration_test.db"
    test_db_url = f"sqlite+aiosqlite:///{test_db_file}"

    # Path to alembic.ini
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    alembic_ini_path = os.path.join(backend_dir, "alembic.ini")

    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    orig_env_db = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_db_url
    try:
        # Test upgrade to head
        command.upgrade(alembic_cfg, "head")

        # Test downgrade to base
        command.downgrade(alembic_cfg, "base")

        # Re-upgrade to head
        command.upgrade(alembic_cfg, "head")
    finally:
        if orig_env_db is not None:
            os.environ["DATABASE_URL"] = orig_env_db
        else:
            os.environ.pop("DATABASE_URL", None)


def test_alembic_migrations_normalizes_raw_database_url(tmp_path):
    """Verify that Alembic migrations normalize raw URLs (like sqlite:// or postgresql://) to async drivers."""
    test_db_file = tmp_path / "migration_raw_test.db"
    # Pass a raw sqlite:// URL without +aiosqlite driver prefix
    raw_db_url = f"sqlite:///{test_db_file}"

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    alembic_ini_path = os.path.join(backend_dir, "alembic.ini")

    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", raw_db_url)

    orig_env_db = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = raw_db_url
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if orig_env_db is not None:
            os.environ["DATABASE_URL"] = orig_env_db
        else:
            os.environ.pop("DATABASE_URL", None)


def test_alembic_env_normalizes_neon_sslmode_url():
    """Verify that Alembic env.py normalizes raw Neon postgresql:// URLs with sslmode=require to asyncpg with ssl=require."""
    from app.core.config import Settings
    from sqlalchemy.engine.url import make_url
    from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg

    raw_neon_url = "postgresql://neondb_owner:mypassword@ep-xyz.singapore.aws.neon.tech/neondb?sslmode=require&channel_binding=prefer"
    normalized = Settings.normalize_database_url(raw_neon_url)

    assert normalized.startswith("postgresql+asyncpg://")
    assert "ssl=require" in normalized
    assert "sslmode" not in normalized
    assert "channel_binding=prefer" in normalized

    # Verify SQLAlchemy asyncpg dialect generates connect args without sslmode keyword error
    parsed_url = make_url(normalized)
    dialect = PGDialect_asyncpg()
    _, connect_kwargs = dialect.create_connect_args(parsed_url)
    assert "sslmode" not in connect_kwargs
    assert connect_kwargs["ssl"] == "require"
    assert connect_kwargs["channel_binding"] == "prefer"


