"""SandboxExecutionRegistry — Child-runtime execution registry mapping implementation_id to concrete execution routines (ADR-032)."""

import os
import time
from collections.abc import Callable, Mapping
from typing import Any

from app.tools.directory_list_tool import DirectoryListTool
from app.tools.file_read_tool import FileReadTool

ToolImplementationCallable = Callable[[Mapping[str, Any], Mapping[str, Any]], Any]


class SandboxExecutionRegistry:
    """Restricted execution registry for child sandbox runtime.

    Invariants (ADR-032):
    1. Independent from Platform ToolRegistry: Does not discover, introspect, or alter platform ToolRegistry.
    2. Explicit Packaging: Only implementations registered in this registry can be executed in the sandbox.
    3. Safe Dispatch: Receives only plain parameters and execution context mapping.
    """

    def __init__(self) -> None:
        self._implementations: dict[str, ToolImplementationCallable] = {}

    def register(self, implementation_id: str, callable_fn: ToolImplementationCallable) -> None:
        """Register an implementation callable under an implementation_id."""
        self._implementations[implementation_id] = callable_fn

    def resolve(self, implementation_id: str) -> ToolImplementationCallable:
        """Resolve implementation callable by implementation_id.

        Raises:
            KeyError: If implementation_id is not registered.
        """
        if implementation_id not in self._implementations:
            raise KeyError(
                f"Implementation '{implementation_id}' is not packaged in the sandbox runtime execution registry"
            )
        return self._implementations[implementation_id]

    def has_implementation(self, implementation_id: str) -> bool:
        """Check if implementation_id exists."""
        return implementation_id in self._implementations


# Built-in production tool wrappers
def _run_file_read(parameters: Mapping[str, Any], context: Mapping[str, Any]) -> Any:
    workspace = context.get("workspace_root", "/tmp")
    tool = FileReadTool(workspace=str(workspace))
    return tool.execute(dict(parameters))


def _run_directory_list(parameters: Mapping[str, Any], context: Mapping[str, Any]) -> Any:
    workspace = context.get("workspace_root", "/tmp")
    tool = DirectoryListTool(workspace=str(workspace))
    return tool.execute(dict(parameters))


# Built-in test execution handlers for sandbox isolation verification
def _run_test_echo(parameters: Mapping[str, Any], _context: Mapping[str, Any]) -> Any:
    return parameters.get("message", "echo")


def _run_test_sleep(parameters: Mapping[str, Any], _context: Mapping[str, Any]) -> Any:
    seconds = float(parameters.get("seconds", 1.0))
    time.sleep(seconds)
    return f"slept {seconds}s"


def _run_test_env_dump(parameters: Mapping[str, Any], _context: Mapping[str, Any]) -> Any:
    keys = parameters.get("keys", [])
    return {k: os.environ.get(k) for k in keys}


def _run_test_output_flood(parameters: Mapping[str, Any], _context: Mapping[str, Any]) -> Any:
    count = int(parameters.get("count", 1000))
    chunk = str(parameters.get("chunk", "A" * 1024))
    # Write directly to stdout to generate immediate pipe output
    import sys

    for _ in range(count):
        sys.stdout.write(chunk)
        sys.stdout.flush()
    return "done_flood"


def _run_test_fork_and_persist(parameters: Mapping[str, Any], _context: Mapping[str, Any]) -> Any:
    """Spawn child and grandchild processes to test process-group cleanup."""
    import subprocess
    import sys

    script = """
import time
import subprocess
import sys

# Grandchild process
p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(60)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pid_file = parameters.get("pid_file")
    if pid_file:
        with open(pid_file, "w") as f:
            f.write(str(proc.pid))
    # Return immediately while child and grandchild continue in background
    return {"child_pid": proc.pid}


def _run_test_raise_error(parameters: Mapping[str, Any], _context: Mapping[str, Any]) -> Any:
    msg = parameters.get("message", "simulated test failure")
    err_type = parameters.get("error_type", "ValueError")
    if err_type == "KeyError":
        raise KeyError(msg)
    if err_type == "PermissionError":
        raise PermissionError(msg)
    raise ValueError(msg)


def create_default_execution_registry() -> SandboxExecutionRegistry:
    """Create and populate the default execution registry."""
    reg = SandboxExecutionRegistry()
    reg.register("file_read_v1", _run_file_read)
    reg.register("directory_list_v1", _run_directory_list)
    # Test harnesses
    reg.register("test_echo", _run_test_echo)
    reg.register("test_sleep", _run_test_sleep)
    reg.register("test_env_dump", _run_test_env_dump)
    reg.register("test_output_flood", _run_test_output_flood)
    reg.register("test_fork_and_persist", _run_test_fork_and_persist)
    reg.register("test_raise_error", _run_test_raise_error)
    return reg


default_execution_registry = create_default_execution_registry()
