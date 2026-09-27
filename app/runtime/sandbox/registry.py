"""SandboxExecutionRegistry — Child-runtime execution registry mapping implementation_id to concrete execution routines (ADR-032)."""

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
def _require_workspace_root(context: Mapping[str, Any]) -> str:
    """Return the confining workspace root, refusing to substitute a default.

    The wrappers previously fell back to ``/tmp``. A workspace root is the boundary a
    tool is confined to, so an absent one is a wiring failure, not a value to guess —
    and because the runner supplies the key as ``None`` when no filesystem capability
    is present, the default was reached as the literal string ``"None"`` rather than as
    ``/tmp`` anyway.
    """
    workspace = context.get("workspace_root")
    if not workspace:
        raise PermissionError(
            "Execution refused: no workspace_root was supplied by the capability "
            "descriptor, so the filesystem boundary is undefined"
        )
    return str(workspace)


def _run_file_read(parameters: Mapping[str, Any], context: Mapping[str, Any]) -> Any:
    tool = FileReadTool(workspace=_require_workspace_root(context))
    return tool.execute(dict(parameters))


def _run_directory_list(parameters: Mapping[str, Any], context: Mapping[str, Any]) -> Any:
    tool = DirectoryListTool(workspace=_require_workspace_root(context))
    return tool.execute(dict(parameters))


def create_default_execution_registry() -> SandboxExecutionRegistry:
    """Create the production execution registry.

    Production implementations only. The registry is an explicit packaging boundary —
    only what it contains can execute in the sandbox — so isolation-verification probes
    live in ``testing_registry`` and are registered only on explicit opt-in.
    """
    reg = SandboxExecutionRegistry()
    reg.register("file_read_v1", _run_file_read)
    reg.register("directory_list_v1", _run_directory_list)
    return reg


default_execution_registry = create_default_execution_registry()
