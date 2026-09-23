"""Tests for the canonical application version and public GET /version endpoint.

Invariants verified:
1. Canonical VERSION file exists, is valid semver, and get_platform_version() matches it.
2. Missing, blank, or malformed VERSION fails closed with VersionError.
3. GET /version returns 200 with {name, version} schema and requires no authentication.
4. /health and /version maintain non-overlapping contracts.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.version import (
    PLATFORM_NAME,
    SEMVER_REGEX,
    VERSION_FILE_PATH,
    VersionError,
    get_platform_version,
)

client = TestClient(app)


class TestCanonicalVersionSource:
    """The root VERSION file is the single machine-readable authority."""

    def test_version_file_exists(self) -> None:
        assert VERSION_FILE_PATH.is_file(), f"Expected VERSION file at {VERSION_FILE_PATH}"

    def test_version_file_is_valid_semver(self) -> None:
        version_str = VERSION_FILE_PATH.read_text(encoding="utf-8").strip()
        assert SEMVER_REGEX.match(version_str) is not None, f"'{version_str}' is not valid semver"

    def test_get_platform_version_returns_canonical_version(self) -> None:
        expected = VERSION_FILE_PATH.read_text(encoding="utf-8").strip()
        assert get_platform_version() == expected
        assert get_platform_version() == "0.15.0"

    def test_missing_version_file_fails_closed(self, tmp_path: Path) -> None:
        missing_file = tmp_path / "NONEXISTENT_VERSION"
        with pytest.raises(VersionError, match="Canonical VERSION file not found"):
            get_platform_version(missing_file)

    def test_empty_version_file_fails_closed(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "VERSION"
        empty_file.write_text("   \n", encoding="utf-8")
        with pytest.raises(VersionError, match="is empty"):
            get_platform_version(empty_file)

    @pytest.mark.parametrize(
        "invalid_version",
        [
            "v0.15.0",      # Leading 'v' is for git tags, not the VERSION file
            "0.15",         # Incomplete semver
            "beta-1",       # Missing major.minor.patch
            "0.15.0.1",     # Too many segments
            "01.0.0",       # Leading zero in major
        ],
    )
    def test_malformed_version_fails_closed(self, tmp_path: Path, invalid_version: str) -> None:
        malformed_file = tmp_path / "VERSION"
        malformed_file.write_text(f"{invalid_version}\n", encoding="utf-8")
        with pytest.raises(VersionError, match="Must follow semantic versioning"):
            get_platform_version(malformed_file)


class TestVersionEndpoint:
    """GET /version is the canonical public metadata endpoint."""

    def test_get_version_returns_200_and_expected_schema(self) -> None:
        response = client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == PLATFORM_NAME
        assert data["version"] == "0.15.0"
        assert data["version"] == get_platform_version()

    def test_get_version_does_not_mix_operational_status(self) -> None:
        """/version answers 'what release is running?', not 'is it healthy?'."""
        response = client.get("/version")
        data = response.json()
        assert "status" not in data

    def test_get_version_is_unauthenticated(self) -> None:
        """Public plane: unauthenticated requests succeed without credentials."""
        # Clean request without any Authorization header
        response = client.get("/version", headers={})
        assert response.status_code == 200

    def test_health_and_version_separation(self) -> None:
        """/health owns health status; /version owns release metadata."""
        health_resp = client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok"}

        version_resp = client.get("/version")
        assert version_resp.status_code == 200
        assert version_resp.json() == {
            "name": PLATFORM_NAME,
            "version": get_platform_version(),
        }
