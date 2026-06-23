import json
import os

from google import genai


class GeminiService:
    """
    Thin wrapper around the Gemini API.

    Responsibilities:

    - Authenticate
    - Send prompts
    - Return parsed JSON

    Not responsible for:

    - Tool selection
    - Authorization
    - Policy evaluation
    - Tool execution
    """

    MODEL = "gemini-2.5-pro"

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set."
            )

        self._client = genai.Client(
            api_key=api_key,
        )

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        response = self._client.models.generate_content(
            model=self.MODEL,
            contents=user_prompt,
            config={
                "system_instruction": system_prompt,
            },
        )

        if response.text is None:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        return json.loads(response.text)