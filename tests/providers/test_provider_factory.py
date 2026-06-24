import pytest

from app.providers.gemini_provider import GeminiProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.provider_factory import ProviderFactory


def test_provider_factory_returns_ollama(monkeypatch):
    monkeypatch.setenv(
        "DEFAULT_PROVIDER",
        "ollama",
    )

    provider = ProviderFactory.create()

    assert isinstance(
        provider,
        OllamaProvider,
    )


def test_provider_factory_returns_gemini(monkeypatch):
    monkeypatch.setenv(
        "DEFAULT_PROVIDER",
        "gemini",
    )

    provider = ProviderFactory.create()

    assert isinstance(
        provider,
        GeminiProvider,
    )


def test_provider_factory_invalid_provider(monkeypatch):
    monkeypatch.setenv(
        "DEFAULT_PROVIDER",
        "invalid",
    )

    with pytest.raises(ValueError):
        ProviderFactory.create()