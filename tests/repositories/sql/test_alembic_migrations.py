"""Verification tests for Alembic schema migrations and model consistency (Plane 3)."""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.repositories.sql.models  # noqa: F401 - Register models
from alembic import command
from app.repositories.sql.base import Base

EXPECTED_TABLES = {
    "agents",
    "tools",
    "agent_enforcement_state",
    "agent_enforcement_transitions",
    "sessions",
    "agent_sequence_counters",
    "session_events",
    "execution_grants",
    "audit_events",
}


@pytest.fixture
def alembic_config(tmp_path: Path) -> tuple[Config, str]:
    """Provide an Alembic Config pointing to a temporary SQLite database."""
    db_path = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_path}"

    repo_root = Path(__file__).resolve().parents[3]
    ini_path = repo_root / "alembic.ini"

    config = Config(str(ini_path))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("script_location", str(repo_root / "alembic"))
    return config, db_url


def test_alembic_upgrade_and_downgrade(alembic_config: tuple[Config, str]) -> None:
    """Verify that Alembic can apply all migrations to head and downgrade to base cleanly."""
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        # 1. Upgrade to head
        command.upgrade(config, "head")

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert EXPECTED_TABLES.issubset(tables)

        # 2. Downgrade to base
        command.downgrade(config, "base")

        inspector = inspect(engine)
        remaining_tables = set(inspector.get_table_names()) - {"alembic_version"}
        assert len(remaining_tables) == 0

    finally:
        engine.dispose()


def test_alembic_schema_matches_base_metadata(alembic_config: tuple[Config, str]) -> None:
    """Verify that the schema produced by Alembic head has zero drift from Base.metadata."""
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "head")

        with engine.connect() as conn:
            migration_ctx = MigrationContext.configure(
                conn,
                opts={"compare_type": True, "compare_server_default": True},
            )
            diff = compare_metadata(migration_ctx, Base.metadata)
            assert diff == [], f"Schema drift detected between migrations and Base.metadata: {diff}"

    finally:
        engine.dispose()
