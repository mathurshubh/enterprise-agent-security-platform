"""Runtime execution and sandbox domain exceptions (ADR-032)."""


class SandboxError(Exception):
    """Base exception for all tool execution sandbox errors."""

    def __init__(self, message: str, tool_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.tool_id = tool_id


class SandboxUnavailableError(SandboxError):
    """Raised when the configured sandbox backend is unconfigured, disabled, or failed to initialize."""


class SandboxTimeoutError(SandboxError):
    """Raised when tool execution exceeds the configured wall-clock timeout deadline."""

    def __init__(
        self,
        message: str,
        tool_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(message, tool_id=tool_id)
        self.timeout_seconds = timeout_seconds


class SandboxResourceExhaustedError(SandboxError):
    """Raised when tool execution breaches memory, CPU, or output size limits."""

    def __init__(
        self,
        message: str,
        tool_id: str | None = None,
        resource_type: str | None = None,
    ) -> None:
        super().__init__(message, tool_id=tool_id)
        self.resource_type = resource_type


class SandboxIsolationError(SandboxError):
    """Raised when a tool execution breaches filesystem, environment, or network egress boundaries."""

    def __init__(
        self,
        message: str,
        tool_id: str | None = None,
        boundary_type: str | None = None,
    ) -> None:
        super().__init__(message, tool_id=tool_id)
        self.boundary_type = boundary_type


class CapabilityDigestMismatchError(SandboxError):
    """Raised when the resolved capability snapshot digest does not match the grant's expected digest."""

    def __init__(
        self,
        message: str,
        expected_digest: str,
        actual_digest: str,
        tool_id: str | None = None,
    ) -> None:
        super().__init__(message, tool_id=tool_id)
        self.expected_digest = expected_digest
        self.actual_digest = actual_digest


class CapabilityProfileNotFoundError(SandboxError):
    """Raised when a referenced capability profile cannot be resolved from registry or provider."""
