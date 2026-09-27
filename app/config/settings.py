"""Application configuration resolved from the process environment.

Security-sensitive configuration fails closed. A value that would weaken a
security control is never defaulted, because a silent default is indistinguishable
from a correct deployment until it is attacked (finding H-1).

Non-security configuration may still carry a safe default.
"""

import os

JWT_SECRET_KEY_ENV_VAR = "JWT_SECRET_KEY"
MINIMUM_JWT_SECRET_LENGTH = 32

# Retired development fallback. This value was shipped as the default signing key
# up to and including 74e8c51, so it is public and any token signed with it must
# be treated as forged. It is rejected explicitly so that copying it into an
# environment variable cannot silently reintroduce H-1.
RETIRED_DEVELOPMENT_SECRET = "development-secret-key-change-in-production-32bytes"

_PROVISIONING_HINT = (
    f"Export {JWT_SECRET_KEY_ENV_VAR} with an explicit secret of at least "
    f"{MINIMUM_JWT_SECRET_LENGTH} bytes before starting the application. "
    "Generate one with: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'. "
    "Note that this application does not load .env files."
)


class ConfigurationError(RuntimeError):
    """Raised when security-sensitive configuration is missing or unusable."""


def get_default_provider() -> str:
    """Return the configured LLM provider.

    Provider selection is not a security control, so it retains a default.
    """
    return os.getenv(
        "DEFAULT_PROVIDER",
        "ollama",
    )


MAX_TERMINAL_EXECUTION_RECEIPTS_ENV_VAR = "EXECUTION_EVIDENCE_MAX_TERMINAL_RECEIPTS"
DEFAULT_MAX_TERMINAL_EXECUTION_RECEIPTS = 10_000


def get_max_terminal_execution_receipts() -> int:
    """Return the configured in-memory execution-history capacity.

    Retention capacity is operational rather than security-sensitive, so it keeps a
    default: an absent bound is the dangerous state, and a configured one is not. The
    default derives from a ~20MB in-process budget at a conservative ~2KB per retained
    receipt; it is an initial operational figure, not a guaranteed memory ceiling, since
    the footprint also includes the grant index, container overhead and interpreter
    memory.

    A malformed or out-of-range override fails closed rather than silently falling back
    to the default, because a deployment that tried to set a bound and failed should not
    look like one that never set it.

    Raises:
        ConfigurationError: if the override is not an integer of at least 1.
    """
    raw = os.getenv(MAX_TERMINAL_EXECUTION_RECEIPTS_ENV_VAR)
    if raw is None or not raw.strip():
        return DEFAULT_MAX_TERMINAL_EXECUTION_RECEIPTS

    try:
        value = int(raw.strip())
    except ValueError:
        raise ConfigurationError(
            f"{MAX_TERMINAL_EXECUTION_RECEIPTS_ENV_VAR} must be an integer, got "
            f"'{raw.strip()}'"
        ) from None

    if value < 1:
        raise ConfigurationError(
            f"{MAX_TERMINAL_EXECUTION_RECEIPTS_ENV_VAR} must be at least 1, got {value}"
        )

    return value


def get_jwt_secret_key() -> str:
    """Return the configured JWT signing key, or fail closed.

    Raises:
        ConfigurationError: if the key is absent, blank, the retired development
            default, or shorter than the minimum length required for HS256.
    """
    secret = os.getenv(JWT_SECRET_KEY_ENV_VAR)

    if secret is None or not secret.strip():
        raise ConfigurationError(
            f"{JWT_SECRET_KEY_ENV_VAR} is not set. The platform will not start with an "
            f"insecure signing key. {_PROVISIONING_HINT}"
        )

    if secret == RETIRED_DEVELOPMENT_SECRET:
        raise ConfigurationError(
            f"{JWT_SECRET_KEY_ENV_VAR} is set to the retired development default, which is "
            f"published in this repository and cannot be trusted. {_PROVISIONING_HINT}"
        )

    if len(secret.encode("utf-8")) < MINIMUM_JWT_SECRET_LENGTH:
        raise ConfigurationError(
            f"{JWT_SECRET_KEY_ENV_VAR} is shorter than the {MINIMUM_JWT_SECRET_LENGTH}-byte "
            f"minimum recommended for HS256 (RFC 7518 section 3.2). {_PROVISIONING_HINT}"
        )

    return secret
