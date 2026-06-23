import os

from app.services.gemini_service import GeminiService


def test_gemini_service_initializes(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    service = GeminiService()

    assert service is not None