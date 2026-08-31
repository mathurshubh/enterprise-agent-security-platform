import os


def get_default_provider() -> str:
    return os.getenv(
        "DEFAULT_PROVIDER",
        "ollama",
    )


def get_jwt_secret_key() -> str:
    return os.getenv(
        "JWT_SECRET_KEY",
        "development-secret-key-change-in-production-32bytes",
    )