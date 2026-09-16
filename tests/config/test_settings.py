"""Configuration resolution tests (finding H-1).

The JWT signing key is security-sensitive configuration: it must be provisioned
explicitly, and every value that would weaken token verification is refused.
"""

import pytest

from app.config.settings import (
    JWT_SECRET_KEY_ENV_VAR,
    MINIMUM_JWT_SECRET_LENGTH,
    RETIRED_DEVELOPMENT_SECRET,
    ConfigurationError,
    get_default_provider,
    get_jwt_secret_key,
)

VALID_SECRET = "x" * MINIMUM_JWT_SECRET_LENGTH


class TestJwtSecretKeyResolution:
    def test_absent_secret_raises_configuration_error(self, monkeypatch) -> None:
        monkeypatch.delenv(JWT_SECRET_KEY_ENV_VAR, raising=False)

        with pytest.raises(ConfigurationError, match="is not set"):
            get_jwt_secret_key()

    @pytest.mark.parametrize("blank", ["", "   ", "\n"])
    def test_blank_secret_raises_configuration_error(
        self, monkeypatch, blank: str
    ) -> None:
        monkeypatch.setenv(JWT_SECRET_KEY_ENV_VAR, blank)

        with pytest.raises(ConfigurationError, match="is not set"):
            get_jwt_secret_key()

    def test_retired_development_default_is_rejected(self, monkeypatch) -> None:
        monkeypatch.setenv(JWT_SECRET_KEY_ENV_VAR, RETIRED_DEVELOPMENT_SECRET)

        with pytest.raises(ConfigurationError, match="retired development default"):
            get_jwt_secret_key()

    def test_secret_below_minimum_length_is_rejected(self, monkeypatch) -> None:
        monkeypatch.setenv(JWT_SECRET_KEY_ENV_VAR, "x" * (MINIMUM_JWT_SECRET_LENGTH - 1))

        with pytest.raises(ConfigurationError, match="shorter than"):
            get_jwt_secret_key()

    def test_explicitly_provisioned_secret_is_returned(self, monkeypatch) -> None:
        monkeypatch.setenv(JWT_SECRET_KEY_ENV_VAR, VALID_SECRET)

        assert get_jwt_secret_key() == VALID_SECRET

    def test_error_message_does_not_disclose_the_configured_value(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv(JWT_SECRET_KEY_ENV_VAR, "short-secret")

        with pytest.raises(ConfigurationError) as exc_info:
            get_jwt_secret_key()

        assert "short-secret" not in str(exc_info.value)


class TestNonSecurityConfiguration:
    def test_provider_selection_retains_a_default(self, monkeypatch) -> None:
        """Provider choice is not a security control and still defaults."""
        monkeypatch.delenv("DEFAULT_PROVIDER", raising=False)

        assert get_default_provider() == "ollama"

    def test_provider_selection_honours_the_environment(self, monkeypatch) -> None:
        monkeypatch.setenv("DEFAULT_PROVIDER", "gemini")

        assert get_default_provider() == "gemini"
