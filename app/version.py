"""Canonical application version resolution.

The application version is defined exclusively by the root ``VERSION`` file.
Git tags remain the release authority, while ``VERSION`` is the sole machine-readable
authority for the application's runtime and build identity.

Fails closed: a missing, blank, or malformed version string is an explicit configuration
error rather than defaulting to "unknown".
"""

import re
from pathlib import Path

VERSION_FILE_PATH = Path(__file__).resolve().parent.parent / "VERSION"
SEMVER_REGEX = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

PLATFORM_NAME = "Enterprise Agent Security Platform"


class VersionError(RuntimeError):
    """Raised when the canonical VERSION file is missing, empty, or invalid."""


def get_platform_version(version_path: Path = VERSION_FILE_PATH) -> str:
    """Read and validate the canonical application version.

    Args:
        version_path: Path to the VERSION file, defaulting to root VERSION.

    Returns:
        The validated semver string.

    Raises:
        VersionError: If the file does not exist, cannot be read, is empty,
            or does not conform to semantic versioning.
    """
    if not version_path.is_file():
        raise VersionError(
            f"Canonical VERSION file not found at '{version_path}'. "
            "Application release identity cannot be established."
        )

    try:
        content = version_path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        raise VersionError(
            f"Failed to read VERSION file at '{version_path}': {exc}"
        ) from exc

    if not content:
        raise VersionError(
            f"Canonical VERSION file at '{version_path}' is empty. "
            "A valid semver string is required."
        )

    if not SEMVER_REGEX.match(content):
        raise VersionError(
            f"Invalid version string '{content}' in '{version_path}'. "
            "Must follow semantic versioning (e.g. '0.15.0')."
        )

    return content
