"""H-1 — Committed default JWT signing secret.

Review evidence (74e8c51)::

    secret in use: 'development-secret-key-change-in-production-32bytes'
    [EXPLOIT] forged ADMIN token w/ default secret -> GET /api/v1/agents = 200

Two facts combine into the finding: configuration fails open to a constant that
is published in this repository, and knowledge of the signing key is sufficient
to mint an ADMIN principal for an arbitrary agent identity.

No new secret is introduced here. The development fallback is read back from
``get_jwt_secret_key()`` rather than duplicated as a literal.
"""

import os
import time

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import jwt_service
from app.config.settings import get_jwt_secret_key
from app.main import app

client = TestClient(app)


def _development_fallback_secret() -> str:
    """Return the value ``get_jwt_secret_key()`` yields with no environment override."""
    previous = os.environ.pop("JWT_SECRET_KEY", None)
    try:
        return get_jwt_secret_key()
    finally:
        if previous is not None:
            os.environ["JWT_SECRET_KEY"] = previous


def _forge(secret: str, role: str = "ADMIN", agent_id: str = "attacker-chosen") -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "sub": "attacker",
            "agent_id": agent_id,
            "role": role,
            "iat": now,
            "exp": now + 3600,
        },
        secret,
        algorithm="HS256",
    )


@pytest.mark.security_baseline
def test_baseline_missing_secret_env_falls_back_to_committed_constant() -> None:
    """Absent configuration yields a key instead of refusing to start."""
    secret = _development_fallback_secret()

    assert isinstance(secret, str)
    assert secret
    assert "development" in secret


@pytest.mark.security_baseline
def test_baseline_token_signed_with_active_key_is_accepted_as_admin() -> None:
    """Anyone holding the signing key mints an accepted ADMIN principal."""
    token = _forge(jwt_service.secret_key)

    response = client.get(
        "/api/v1/agents", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200


@pytest.mark.security_invariant
@pytest.mark.xfail(
    strict=True,
    reason="H-1: configuration fails open; hardening must refuse to start without JWT_SECRET_KEY",
)
def test_invariant_missing_secret_must_fail_closed(monkeypatch) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises((RuntimeError, ValueError)):
        get_jwt_secret_key()


@pytest.mark.security_invariant
@pytest.mark.skipif(
    jwt_service.secret_key != _development_fallback_secret(),
    reason="Deployment overrides JWT_SECRET_KEY; the legacy-default attack is not applicable",
)
@pytest.mark.xfail(
    strict=True,
    reason="H-1: tokens signed with the published development default are still accepted",
)
def test_invariant_token_signed_with_legacy_default_is_rejected() -> None:
    token = _forge(_development_fallback_secret())

    response = client.get(
        "/api/v1/agents", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
