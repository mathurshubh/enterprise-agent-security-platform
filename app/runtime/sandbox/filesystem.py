"""Filesystem access enforcement for process-level sandbox execution (ADR-032).

Security Hierarchy:
- Level 1: Policy Authorization (PolicyEngine) — Answers: Is this resource/action allowed?
- Level 2: Process-Level Enforcement (FilesystemSandboxGuard) — Answers: Does ordinary tool code
  attempting filesystem access stay within its declared capability?
- Level 3: Strong OS Isolation (Container / MicroVM Sandbox Backend) — Answers: Can the process
  physically access host filesystem resources outside its sandbox?

Explicit Non-Goal:
The v0.17 local process backend does not claim kernel-enforced filesystem isolation or
protection against a sufficiently privileged or native sandbox escape. It provides
process-level capability containment for standard Python tool code.
Under the supported threat model, the guard prevents ordinary path traversal, absolute-path
access, and straightforward symlink escapes. It does not claim race-free hostile filesystem
isolation against concurrent symlink modifications.
"""

import os
import sys
from pathlib import Path
from types import TracebackType
from typing import Any, Mapping, Self


def _sanitize_path_in_message(path: str) -> str:
    """Redact raw filesystem paths from diagnostic and error messages."""
    return "[REDACTED_PATH]"


class FilesystemSandboxGuard:
    """Enforces process-level filesystem access controls during tool execution.

    Invariants:
    1. Working directory pinned to workspace root.
    2. Path Traversal & Absolute Path Prevention: All attempted paths are canonicalized
       and verified to reside within workspace_root.
    3. Symlink Escapes: Target paths resolved through symlinks must remain within workspace_root.
    4. Subpath Enforcement: When allowed_subpaths is specified, access is restricted to those subpaths.
    5. Read-Only Enforcement: When read_only is True, all mutation operations (write, mkdir,
       remove, rename, chmod, symlink) are blocked.
    6. Ephemeral Scratch: When allow_temp_writes is True, writes are permitted strictly within
       an isolated scratch directory.
    """

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        allowed_subpaths: tuple[str, ...] = (),
        read_only: bool = True,
        allow_temp_writes: bool = False,
        scratch_dir: str | Path | None = None,
        platform_root: str | Path | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.allowed_subpaths = tuple(allowed_subpaths)
        self.read_only = read_only
        self.allow_temp_writes = allow_temp_writes
        self.scratch_dir = Path(scratch_dir).resolve() if scratch_dir else None
        self.platform_root = Path(platform_root).resolve() if platform_root else None

        # Determine standard library / runtime paths permitted for read-only interpreter needs
        runtime_dirs: list[Path] = []
        for p in (sys.base_prefix, sys.prefix, sys.exec_prefix):
            if p:
                try:
                    runtime_dirs.append(Path(p).resolve())
                except Exception:
                    pass
        self._runtime_dirs = tuple(runtime_dirs)
        self._active = False
        self._installed = False

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        scratch_dir: str | None = None,
        platform_root: str | Path | None = None,
    ) -> "FilesystemSandboxGuard":
        """Construct guard from serialized capability dictionary."""
        return cls(
            workspace_root=data["workspace_root"],
            allowed_subpaths=tuple(data.get("allowed_subpaths", ())),
            read_only=data.get("read_only", True),
            allow_temp_writes=data.get("allow_temp_writes", False),
            scratch_dir=scratch_dir,
            platform_root=platform_root,
        )

    @property
    def is_active(self) -> bool:
        return self._active

    def activate(self) -> None:
        self._active = True

    def deactivate(self) -> None:
        self._active = False

    def __enter__(self) -> Self:
        self.activate()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.deactivate()

    def check_access(self, target: Any, *, is_write: bool = False) -> None:
        """Validate an attempted filesystem access against the active capabilities.

        Raises:
            PermissionError: If the access breaches capability constraints.
        """
        if not self._active:
            return

        if target is None or isinstance(target, int):
            # Integer file descriptors (e.g. 0, 1, 2) or None are skipped
            return

        try:
            if isinstance(target, bytes):
                target_str = os.fsdecode(target)
            else:
                target_str = str(target)

            if not target_str.strip():
                return

            if target_str in (os.devnull, "/dev/null"):
                return

            target_path = Path(target_str)
            if not target_path.is_absolute():
                resolved = (self.workspace_root / target_path).resolve()
            else:
                resolved = target_path.resolve()
        except Exception as exc:
            raise PermissionError(
                f"Invalid path access: {_sanitize_path_in_message(str(target))}"
            ) from exc

        # Disallow access to sensitive environment/secret files anywhere
        name_lower = resolved.name.lower()
        if (
            resolved.name.startswith(".env")
            or "jwt" in name_lower
            or "secret" in name_lower
            or "password" in name_lower
        ):
            raise PermissionError(
                f"Access to sensitive file forbidden: {_sanitize_path_in_message(str(target))}"
            )

        # Block access to platform repository internals if outside workspace
        if self.platform_root and resolved.is_relative_to(self.platform_root):
            if not resolved.is_relative_to(self.workspace_root):
                raise PermissionError(
                    "Access to platform internals outside workspace forbidden: "
                    f"{_sanitize_path_in_message(str(target))}"
                )

        if is_write:
            # 1. Check mutation in read-only mode
            if self.read_only:
                if self.allow_temp_writes and self.scratch_dir:
                    if not resolved.is_relative_to(self.scratch_dir):
                        raise PermissionError(
                            "Filesystem write forbidden in read-only sandbox outside scratch: "
                            f"{_sanitize_path_in_message(str(target))}"
                        )
                    return
                raise PermissionError(
                    "Filesystem modification is forbidden in read-only sandbox: "
                    f"{_sanitize_path_in_message(str(target))}"
                )

            # 2. Check mutation in read-write mode
            if self.scratch_dir and resolved.is_relative_to(self.scratch_dir):
                return

            if not resolved.is_relative_to(self.workspace_root):
                raise PermissionError(
                    f"Filesystem write outside workspace is forbidden: {_sanitize_path_in_message(str(target))}"
                )

            if self.allowed_subpaths:
                in_subpath = any(
                    resolved.is_relative_to(self.workspace_root / sub)
                    for sub in self.allowed_subpaths
                )
                if not in_subpath:
                    raise PermissionError(
                        "Filesystem write outside allowed subpaths is forbidden: "
                        f"{_sanitize_path_in_message(str(target))}"
                    )
            return

        # Read operations
        # 1. Scratch directory access
        if self.scratch_dir and resolved.is_relative_to(self.scratch_dir):
            return

        # 2. Workspace root access
        if resolved.is_relative_to(self.workspace_root):
            if self.allowed_subpaths:
                in_subpath = any(
                    resolved.is_relative_to(self.workspace_root / sub)
                    or (self.workspace_root / sub).is_relative_to(resolved)
                    for sub in self.allowed_subpaths
                )
                if not in_subpath and resolved != self.workspace_root:
                    raise PermissionError(
                        "Filesystem read outside allowed subpaths is forbidden: "
                        f"{_sanitize_path_in_message(str(target))}"
                    )
            return

        # 3. Python runtime / standard library (read-only for interpreter operation)
        if any(resolved.is_relative_to(rd) for rd in self._runtime_dirs):
            return

        # Deny access outside workspace
        raise PermissionError(
            f"Filesystem read outside workspace is forbidden: {_sanitize_path_in_message(str(target))}"
        )

    def audit_hook(self, event: str, args: tuple[Any, ...]) -> None:
        """CPython audit hook callback dispatched on low-level OS operations."""
        if not self._active:
            return

        if event == "open":
            path = args[0] if len(args) > 0 else None
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0

            is_write = False
            if isinstance(mode, str):
                if any(c in mode for c in ("w", "a", "x", "+")):
                    is_write = True
            elif isinstance(flags, int):
                write_mask = (
                    os.O_WRONLY
                    | os.O_RDWR
                    | getattr(os, "O_CREAT", 0)
                    | getattr(os, "O_APPEND", 0)
                    | getattr(os, "O_TRUNC", 0)
                )
                if flags & write_mask:
                    is_write = True

            self.check_access(path, is_write=is_write)

        elif event in ("os.listdir", "os.scandir"):
            path = args[0] if args else None
            self.check_access(path, is_write=False)

        elif event in ("os.mkdir", "os.rmdir", "os.remove", "os.unlink", "os.chmod"):
            path = args[0] if args else None
            self.check_access(path, is_write=True)

        elif event in ("os.rename", "os.replace"):
            src = args[0] if len(args) > 0 else None
            dst = args[1] if len(args) > 1 else None
            self.check_access(src, is_write=True)
            self.check_access(dst, is_write=True)

        elif event in ("os.symlink", "os.link"):
            src = args[0] if len(args) > 0 else None
            dst = args[1] if len(args) > 1 else None
            self.check_access(dst, is_write=True)
            self.check_access(src, is_write=False)

    def install(self) -> None:
        """Register the audit hook with the CPython runtime."""
        if not self._installed:
            sys.addaudithook(self.audit_hook)
            self._installed = True
