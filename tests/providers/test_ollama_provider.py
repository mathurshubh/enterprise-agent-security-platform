from app.providers.ollama_provider import OllamaProvider

from app.services.ollama_service import OllamaService


class FakeOllamaService(OllamaService):

    def __init__(self):
        pass

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        return {
            "tool_id": "file_read",
            "parameters": {
                "path": "notes.txt",
            },
        }


def test_ollama_provider_delegates_to_service():
    provider = OllamaProvider(
        ollama_service=FakeOllamaService(),
    )

    response = provider.chat(
        "system",
        "read notes.txt",
    )

    assert response == {
        "tool_id": "file_read",
        "parameters": {
            "path": "notes.txt",
        },
    }