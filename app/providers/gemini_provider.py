from app.providers.provider_adapter import ProviderAdapter
from app.services.gemini_service import GeminiService


class GeminiProvider(ProviderAdapter):
    """
    Provider adapter for Google's Gemini models.

    This class delegates communication to GeminiService while exposing
    the provider-agnostic ProviderAdapter interface.
    """

    def __init__(
        self,
        gemini_service: GeminiService | None = None,
    ) -> None:
        self._gemini_service = (
            gemini_service
            or GeminiService()
        )
        
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        return self._gemini_service.chat(
            system_prompt,
            user_prompt,
        )