import os


def get_default_provider() -> str:
    return os.getenv(
        "DEFAULT_PROVIDER",
        "ollama",
    )