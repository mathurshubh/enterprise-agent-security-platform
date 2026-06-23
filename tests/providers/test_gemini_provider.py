from app.providers.gemini_provider import GeminiProvider
from app.services.gemini_service import GeminiService


class FakeGeminiService(GeminiService):
    def __init__(self) -> None:
        # Prevent initialization of the real Gemini client.
        pass

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        return {
            "tool_id": "directory_list",
            "parameters": {
                "path": ".",
            },
        }


def test_gemini_provider_delegates_to_service():
    provider = GeminiProvider(
        gemini_service=FakeGeminiService(),
    )

    response = provider.chat(
        "system",
        "list files",
    )

    assert response == {
        "tool_id": "directory_list",
        "parameters": {
            "path": ".",
        },
    }