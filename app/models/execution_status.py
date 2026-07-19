from enum import Enum


class ExecutionStatus(str, Enum):
    """Represents the system-level state of a scenario execution."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
