from enum import Enum


class ExecutionMode(str, Enum):
    """Specifies the pathway used to execute a security scenario."""

    PROMPT = "PROMPT"
    TOOL_SEQUENCE = "TOOL_SEQUENCE"
