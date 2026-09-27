"""Runtime execution sandbox infrastructure (ADR-032)."""

from app.runtime.sandbox.descriptor import ToolExecutionDescriptor
from app.runtime.sandbox.process_sandbox import ProcessToolExecutionSandbox
from app.runtime.sandbox.registry import (
    SandboxExecutionRegistry,
    default_execution_registry,
)

__all__ = [
    "ProcessToolExecutionSandbox",
    "SandboxExecutionRegistry",
    "ToolExecutionDescriptor",
    "default_execution_registry",
]
