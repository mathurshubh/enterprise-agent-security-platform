"""The composition root refuses an invalid topology at startup (ADR-030 DB.5, L.6)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config.settings import ConfigurationError, get_repository_backend

# Derived, not hardcoded: the suite runs on developer machines and on CI runners, and an
# absolute path works only on the first. Caught by CI, which is the environment the
# hardcoded path excluded.
PROJECT = Path(__file__).resolve().parents[2]


def _start(env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    """Import the composition root in a fresh process.

    A subprocess rather than a monkeypatched import, because the thing under test is what
    happens when the platform *starts*. Re-importing a module in-process would exercise
    import caching rather than startup.
    """
    # A minimal environment, plus whatever the OS needs to run the interpreter at all.
    # PATH is inherited rather than fixed, because the interpreter location differs
    # between a local .venv and a CI runner's toolchain.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "JWT_SECRET_KEY": "k" * 48,
        **env_extra,
    }
    return subprocess.run(
        # ``sys.executable`` is the interpreter already running the suite, so the
        # subprocess cannot drift from it.
        [sys.executable, "-c", "import app.api.dependencies"],
        cwd=str(PROJECT),
        capture_output=True,
        text=True,
        env=env,
    )


def test_the_default_backend_is_memory() -> None:
    """Persistence is stated, not inferred from the presence of a database URL."""
    assert get_repository_backend() == "memory"


@pytest.mark.security_invariant
def test_the_platform_starts_on_the_default_composition() -> None:
    """The positive half: the refusal below must not be refusing everything."""
    result = _start({})
    assert result.returncode == 0, result.stderr[-2000:]


@pytest.mark.security_invariant
def test_a_durable_backend_is_refused_at_startup_with_its_reason() -> None:
    """L.6 requirement 1, enforced where the platform actually becomes a topology.

    The refusal is the current correct behaviour, not a gap: findings have no repository,
    so a durable composition would pair a durable watermark with a volatile allocator and
    silently lose detection after a restart. Startup failure with a named reason is the
    alternative to that.

    Asserted on the message as well as the exit code, because a startup failure an
    operator cannot diagnose is only marginally better than the silent loss it prevents.
    """
    result = _start(
        {"REPOSITORY_BACKEND": "sql", "DATABASE_URL": "sqlite:///:memory:"}
    )

    assert result.returncode != 0
    assert "DurableCompositionError" in result.stderr
    assert "Finding.evidence_sequence" in result.stderr
    assert "L.6" in result.stderr


@pytest.mark.security_invariant
def test_an_unrecognised_backend_is_refused_rather_than_defaulted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo must not silently produce an in-memory platform."""
    monkeypatch.setenv("REPOSITORY_BACKEND", "postgres")
    with pytest.raises(ConfigurationError, match="not a supported persistence backend"):
        get_repository_backend()


@pytest.mark.security_invariant
def test_a_durable_backend_without_a_database_url_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No development fallback: a durable-looking composition pointed at a throwaway
    database is worse than refusing to start."""
    from app.config.settings import get_database_url

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        get_database_url()


def test_the_composition_root_exposes_the_administrative_plane() -> None:
    """F-09.C/D wired through: the authority the authorization path consults is present."""
    from app.api import dependencies

    assert dependencies.administrative_repository is not None
    assert dependencies.administrative_audit_repository is not None
    assert (
        dependencies.agent_service.administrative_repository
        is dependencies.administrative_repository
    )
