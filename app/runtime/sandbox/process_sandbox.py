"""ProcessToolExecutionSandbox — Isolated subprocess sandbox implementing ToolExecutionSandboxProtocol (ADR-032)."""

import hashlib
import json
import os
import select
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.models.execution_capability import ExecutionCapabilities
from app.models.runtime_context import RuntimeContext
from app.models.sandbox_execution_result import SandboxExecutionResult
from app.runtime.exceptions import (
    SandboxResourceExhaustedError,
    SandboxTimeoutError,
    SandboxUnavailableError,
)
from app.tools.base_tool import BaseTool


def _kill_process_group(pgid: int) -> None:
    """Terminate an entire OS process group with SIGTERM followed by SIGKILL."""
    try:
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(0.05)
    except (ProcessLookupError, PermissionError):
        return

    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


class ProcessToolExecutionSandbox:
    """Subprocess execution sandbox providing process-level capability containment.

    Invariants (ADR-032):
    1. Independent Subprocess: Runs in a separate OS process with its own address space.
    2. Process Group Isolation: Executes under a dedicated session/process group (start_new_session=True).
    3. Clean-Room Environment: Strips parent process environment; explicit allowlist only.
    4. Bounded Output Collection: Output size capped during collection, killing process on breach.
    5. Hard Wall-Clock Timeout: Monotonic deadline enforced via process-group termination.
    6. Guaranteed Cleanup: No sandbox execution returns while its process group remains alive.
    """

    def __init__(self, platform_root: Path | None = None) -> None:
        if platform_root is None:
            # Resolve repository root
            platform_root = Path(__file__).resolve().parent.parent.parent.parent
        self._platform_root = platform_root

    def execute(
        self,
        *,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        capabilities: ExecutionCapabilities,
        context: RuntimeContext,
    ) -> SandboxExecutionResult:
        """Execute an authorized tool within the isolated subprocess sandbox."""
        start_monotonic = time.monotonic()

        # 1. Resolve implementation_id
        implementation_id = getattr(tool, "implementation_id", None)
        if not implementation_id:
            implementation_id = f"{tool.tool_id}_v1"

        # 2. Build ToolExecutionDescriptor payload
        from app.runtime.sandbox.descriptor import ToolExecutionDescriptor

        descriptor = ToolExecutionDescriptor(
            tool_id=tool.tool_id,
            implementation_id=implementation_id,
            parameters=parameters,
            grant_id=context.request_id,
            session_id=context.session_id,
            agent_id=context.authenticated_agent,
            request_id=context.request_id,
        )
        payload_bytes = descriptor.to_json().encode("utf-8")

        # 3. Construct clean-room environment
        env: dict[str, str] = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": str(self._platform_root),
        }
        # Add explicitly allowed environment variables
        for k, v in capabilities.environment_variables.items():
            env[k] = v

        # 4. OS resource limits preexec helper (best-effort)
        def _apply_rlimits() -> None:
            try:
                import resource

                mem_bytes = capabilities.resources.max_memory_bytes
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                cpu_secs = int(capabilities.resources.max_cpu_seconds) + 1
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_secs, cpu_secs + 1))
            except (ImportError, ValueError, OSError):
                pass

        # 5. Launch isolated subprocess
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "app.runtime.sandbox.runner"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True,
                preexec_fn=_apply_rlimits if os.name == "posix" else None,
            )
            pgid = proc.pid
        except Exception as exc:
            raise SandboxUnavailableError(
                f"Failed to launch sandbox subprocess for tool '{tool.tool_id}': {exc}",
                tool_id=tool.tool_id,
            ) from exc

        # 6. Stream input and collect output under bounded limits
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        total_output_bytes = 0
        max_output_bytes = capabilities.resources.max_output_bytes
        timeout_seconds = capabilities.resources.wall_clock_timeout_seconds
        deadline = start_monotonic + timeout_seconds

        try:
            # Write input descriptor to stdin and close pipe
            if proc.stdin is not None:
                proc.stdin.write(payload_bytes)
                proc.stdin.close()

            # Make stdout/stderr non-blocking so reads never hang if descendants hold pipes
            assert proc.stdout is not None
            assert proc.stderr is not None
            os.set_blocking(proc.stdout.fileno(), False)
            os.set_blocking(proc.stderr.fileno(), False)
            read_fds = [proc.stdout.fileno(), proc.stderr.fileno()]

            while True:
                remaining_time = deadline - time.monotonic()
                if remaining_time <= 0:
                    _kill_process_group(pgid)
                    raise SandboxTimeoutError(
                        f"Tool '{tool.tool_id}' exceeded wall-clock timeout of {timeout_seconds}s",
                        tool_id=tool.tool_id,
                        timeout_seconds=timeout_seconds,
                    )

                rlist, _, _ = select.select(read_fds, [], [], min(remaining_time, 0.05))
                for fd in rlist:
                    if fd == proc.stdout.fileno():
                        chunk = proc.stdout.read()
                        if chunk:
                            total_output_bytes += len(chunk)
                            stdout_chunks.append(chunk)
                    elif fd == proc.stderr.fileno():
                        chunk = proc.stderr.read()
                        if chunk:
                            total_output_bytes += len(chunk)
                            stderr_chunks.append(chunk)

                if total_output_bytes > max_output_bytes:
                    _kill_process_group(pgid)
                    raise SandboxResourceExhaustedError(
                        f"Tool '{tool.tool_id}' exceeded output size limit of {max_output_bytes} bytes",
                        tool_id=tool.tool_id,
                        resource_type="max_output_bytes",
                    )

                # Check process completion
                if proc.poll() is not None:
                    # Drain remaining bytes non-blockingly
                    try:
                        rest_stdout = proc.stdout.read()
                        if rest_stdout:
                            total_output_bytes += len(rest_stdout)
                            stdout_chunks.append(rest_stdout)
                    except (OSError, ValueError):
                        pass

                    try:
                        rest_stderr = proc.stderr.read()
                        if rest_stderr:
                            total_output_bytes += len(rest_stderr)
                            stderr_chunks.append(rest_stderr)
                    except (OSError, ValueError):
                        pass

                    if total_output_bytes > max_output_bytes:
                        _kill_process_group(pgid)
                        raise SandboxResourceExhaustedError(
                            f"Tool '{tool.tool_id}' exceeded output size limit of {max_output_bytes} bytes",
                            tool_id=tool.tool_id,
                            resource_type="max_output_bytes",
                        )
                    break

            proc.wait()
            duration_ms = int((time.monotonic() - start_monotonic) * 1000)

        finally:
            # Guarantees process-group cleanup invariant
            _kill_process_group(pgid)
            try:
                proc.wait(timeout=1.0)
            except Exception:
                pass

        # 7. Parse result payload from stdout
        raw_stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace").strip()
        if not raw_stdout:
            raw_stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
            return SandboxExecutionResult(
                success=False,
                output=None,
                output_digest=None,
                exit_code=proc.returncode,
                duration_ms=duration_ms,
                error_type="EmptyOutputError",
                error_message=raw_stderr or "No output returned from sandbox runner.",
            )

        try:
            parsed = json.loads(raw_stdout)
            output = parsed.get("output")
            output_digest = None
            if output is not None:
                output_digest = hashlib.sha256(
                    json.dumps(output, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()

            return SandboxExecutionResult(
                success=parsed.get("success", False),
                output=output,
                output_digest=output_digest,
                exit_code=parsed.get("exit_code", proc.returncode),
                duration_ms=duration_ms,
                error_type=parsed.get("error_type"),
                error_message=parsed.get("error_message"),
                resource_usage={"duration_ms": duration_ms, "output_bytes": total_output_bytes},
            )
        except json.JSONDecodeError as exc:
            return SandboxExecutionResult(
                success=False,
                output=None,
                output_digest=None,
                exit_code=proc.returncode,
                duration_ms=duration_ms,
                error_type="JSONDecodeError",
                error_message=f"Failed to parse runner output: {exc}",
            )
