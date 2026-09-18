"""Local development credentials (scripts/dev_credentials.py, scripts/dev-start.sh).

The startup script is a developer-experience convenience, so these tests assert that it
cannot become a hole in the authentication boundary: the token it mints is an ordinary
JWT the backend verifies normally, it is worthless against a backend running a different
secret, and the startup output never reveals either value.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt_service import JWTService
from app.config.settings import get_jwt_secret_key
from app.main import app
from app.models.jwt_claims import Role
from scripts.dev_credentials import (
    DEFAULT_LIFETIME_MINUTES,
    DEFAULT_ROLE,
    build_parser,
    generate_secret,
    main,
    mint_dev_token,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEV_START = REPO_ROOT / "scripts" / "dev-start.sh"
PROTECTED_ENDPOINT = "/api/v1/agents"

client = TestClient(app)


class TestCredentialGeneration:
    def test_defaults_are_least_privileged_and_day_scoped(self) -> None:
        assert DEFAULT_ROLE == Role.ANALYST
        assert DEFAULT_LIFETIME_MINUTES == 24 * 60

    def test_generated_secret_is_accepted_by_platform_validation(self, monkeypatch) -> None:
        secret = generate_secret()
        monkeypatch.setenv("JWT_SECRET_KEY", secret)

        assert get_jwt_secret_key() == secret
        assert secret != generate_secret()

    def test_token_verifies_under_the_secret_it_was_minted_from(self) -> None:
        secret = generate_secret()

        token = mint_dev_token(secret)
        claims = JWTService(secret_key=secret).verify_token(token)

        assert claims.role == Role.ANALYST
        assert (claims.exp - claims.iat) == DEFAULT_LIFETIME_MINUTES * 60

    def test_token_is_worthless_under_a_different_secret(self) -> None:
        token = mint_dev_token(generate_secret())

        with pytest.raises(ValueError):
            JWTService(secret_key=generate_secret()).verify_token(token)

    def test_admin_role_is_available_only_when_requested(self) -> None:
        secret = generate_secret()

        default_claims = JWTService(secret_key=secret).verify_token(mint_dev_token(secret))
        admin_claims = JWTService(secret_key=secret).verify_token(
            mint_dev_token(secret, role=Role.ADMIN)
        )

        assert default_claims.role == Role.ANALYST
        assert admin_claims.role == Role.ADMIN

    def test_cli_offers_only_console_roles(self) -> None:
        """AGENT is a runtime principal, not a console role, so it is not selectable."""
        parser = build_parser()

        assert parser.parse_args(["token"]).role == Role.ANALYST.value
        assert parser.parse_args(["token", "--role", "ADMIN"]).role == Role.ADMIN.value

        with pytest.raises(SystemExit):
            parser.parse_args(["token", "--role", "AGENT"])


class TestAuthenticationBoundary:
    """The generated token must work, and nothing else may."""

    def test_generated_token_is_accepted_by_a_protected_endpoint(self) -> None:
        token = mint_dev_token(get_jwt_secret_key())

        response = client.get(
            PROTECTED_ENDPOINT, headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    def test_missing_token_is_refused(self) -> None:
        response = client.get(PROTECTED_ENDPOINT)

        assert response.status_code == 401
        assert response.json()["detail"] == "Missing authorization credentials"

    def test_malformed_token_is_refused(self) -> None:
        response = client.get(
            PROTECTED_ENDPOINT, headers={"Authorization": "Bearer not-a-jwt"}
        )

        assert response.status_code == 401

    def test_token_from_another_secret_is_refused(self) -> None:
        foreign_token = mint_dev_token(generate_secret())

        response = client.get(
            PROTECTED_ENDPOINT, headers={"Authorization": f"Bearer {foreign_token}"}
        )

        assert response.status_code == 401
        assert "Invalid token" in response.json()["detail"]


class TestOutputDoesNotLeak:
    def test_summary_redacts_the_secret_and_the_token(self, capsys, monkeypatch) -> None:
        secret = generate_secret()
        token = mint_dev_token(secret)
        monkeypatch.setenv("JWT_SECRET_KEY", secret)
        monkeypatch.setenv("EASP_DEV_API_TOKEN", token)

        assert main(["summary"]) == 0

        output = capsys.readouterr().out
        assert secret not in output
        assert token not in output
        assert "<redacted" in output

    @pytest.mark.skipif(
        not (REPO_ROOT / "frontend" / "node_modules").is_dir(),
        reason="dry run performs frontend preflight; requires installed frontend dependencies",
    )
    def test_dry_run_prints_no_secret_or_token(self) -> None:
        environment = dict(os.environ)
        environment["EASP_DEV_PYTHON"] = sys.executable
        # Ports the dry run only probes; keep away from a running environment.
        environment["BACKEND_PORT"] = "8931"
        environment["FRONTEND_PORT"] = "8932"
        environment.pop("JWT_SECRET_KEY", None)
        environment.pop("EASP_DEV_API_TOKEN", None)

        completed = subprocess.run(
            [str(DEV_START), "--dry-run"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            env=environment,
        )

        assert completed.returncode == 0, completed.stderr
        combined = completed.stdout + completed.stderr
        assert "<redacted" in combined
        assert "Dry run complete" in combined
        # A JWT is three base64url segments; none may appear in the output.
        assert "eyJ" not in combined
