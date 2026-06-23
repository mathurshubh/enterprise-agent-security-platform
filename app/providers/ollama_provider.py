from app.providers.provider_adapter import ProviderAdapter
from app.services.ollama_service import OllamaService


class OllamaProvider(ProviderAdapter):
    """
    Provider adapter for Ollama.

    This class delegates HTTP communication to OllamaService while
    exposing the provider-agnostic ProviderAdapter interface.
    """

    def __init__(
        self,
        ollama_service: OllamaService | None = None,
    ) -> None:
        self._ollama_service = (
            ollama_service
            or OllamaService()
        )
        
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        return self._ollama_service.chat(
            system_prompt,
            user_prompt,
        )