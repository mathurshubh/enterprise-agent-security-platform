import json

import requests


class OllamaService:
    def __init__(
        self,
        model: str = "llama3.2:3b",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._base_url = base_url

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        response = requests.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
                "stream": False,
            },
            timeout=30,
        )

        response.raise_for_status()

        payload = response.json()

        content = payload["message"]["content"]

        return json.loads(content)