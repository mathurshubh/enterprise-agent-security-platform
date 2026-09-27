"""Runtime execution and sandbox domain exceptions (ADR-032)."""


class ExecutionEvidenceError(Exception):
    """Base exception for failures of the execution evidence boundary.

    Deliberately **not** a ``SandboxError``. A sandbox error means the isolation
    boundary failed; an evidence error means the platform could not record what the
    execution boundary observed. Collapsing them would let an evidence failure be
    categorised as an isolation failure in the very receipt that could not be written.

    The two axes stay separate: *execution outcome* is what happened in the sandbox,
    *evidence integrity* is whether the platform recorded it.
    """

    def __init__(
        self,
        message: str,
        tool_id: str | None = None,
        receipt_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.tool_id = tool_id
        self.receipt_id = receipt_id


class ExecutionEvidenceUnavailableError(ExecutionEvidenceError):
    """Raised when STARTED evidence cannot be recorded, before the sandbox is invoked.

    A pre-execution fail-closed condition (N3-3): nothing executed, so no side effect
    exists. Distinct from ExecutionEvidenceIntegrityError precisely because that
    distinction is the difference between "an execution was prevented" and "an
    execution happened and was not recorded".
    """


class ExecutionEvidenceIntegrityError(ExecutionEvidenceError):
    """Raised when terminal evidence cannot be recorded after execution occurred.

    The execution cannot be rolled back, so this is never reported as success. Where the
    execution itself also failed, that failure stays primary and this is retained as
    secondary information on it, because an evidence fault must not erase the outcome it
    was trying to record.
    """


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
