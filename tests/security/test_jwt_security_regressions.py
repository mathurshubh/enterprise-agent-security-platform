"""H-1 — JWT signing key configuration.

Baseline recorded at 74e8c51: configuration fell back to a constant published in
this repository, so any reader could mint an ADMIN principal that the platform
accepted::

    secret in use: 'development-secret-key-change-in-production-32bytes'
    [EXPLOIT] forged ADMIN token w/ default secret -> GET /api/v1/agents = 200

Hardened in ``feat/jwt-config-hardening``: ``get_jwt_secret_key()`` fails closed,
and ``app.api.dependencies`` resolves the key at import time, so an unconfigured
deployment cannot start. The two contracts that were recorded as ``xfail``
invariants at the baseline are now enforced assertions.

The retired secret is imported from ``app.config.settings`` rather than restated
here: it exists in the codebase as a rejected value, so the corpus needs no copy
of it.
"""

import time

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import jwt_service
from app.config.settings import (
    JWT_SECRET_KEY_ENV_VAR,
    RETIRED_DEVELOPMENT_SECRET,
    ConfigurationError,
    get_jwt_secret_key,
)
from app.main import app

client = TestClient(app)


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


@pytest.mark.security_invariant
def test_invariant_missing_secret_fails_closed(monkeypatch) -> None:
    """Promoted from xfail: absent configuration must refuse to yield a key.

    ``app.api.dependencies`` calls this at import time, so this failure is the
    application's startup failure.
    """
    monkeypatch.delenv(JWT_SECRET_KEY_ENV_VAR, raising=False)

    with pytest.raises(ConfigurationError):
        get_jwt_secret_key()


@pytest.mark.security_invariant
def test_invariant_token_signed_with_retired_default_is_rejected() -> None:
    """Promoted from xfail: the published legacy key can no longer authenticate.

    No skip guard is needed any more. The retired value is refused by
    configuration, so it can never be the active signing key.
    """
    token = _forge(RETIRED_DEVELOPMENT_SECRET)

    response = client.get(
        "/api/v1/agents", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


@pytest.mark.security_regression
def test_retired_default_is_never_the_active_signing_key() -> None:
    assert jwt_service.secret_key != RETIRED_DEVELOPMENT_SECRET


@pytest.mark.security_regression
def test_token_signed_with_the_configured_key_is_accepted() -> None:
    """Positive control: hardening did not break the authentication path.

    Holding the configured signing key still mints an accepted principal — that
    is how HS256 works. It was only a finding while the key was public.
    """
    token = _forge(jwt_service.secret_key)

    response = client.get(
        "/api/v1/agents", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
