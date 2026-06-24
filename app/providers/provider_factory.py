from app.config import settings
from app.providers.gemini_provider import GeminiProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.provider_adapter import ProviderAdapter


class ProviderFactory:
    """
    Creates ProviderAdapter implementations.

    The factory isolates provider selection from the rest of the
    application.
    """

    @staticmethod
    def create() -> ProviderAdapter:
        provider = settings.get_default_provider()

        if provider == "ollama":
            return OllamaProvider()

        if provider == "gemini":
            return GeminiProvider()

        raise ValueError(
            f"Unsupported provider: {provider}"
        )