"""Sandbox Runner — Headless subprocess entrypoint executing tool descriptors (ADR-032)."""

import json
import re
import sys
from typing import Any

from app.runtime.sandbox.descriptor import ToolExecutionDescriptor
from app.runtime.sandbox.registry import default_execution_registry


def sanitize_error_message(msg: str) -> str:
    """Sanitize error messages to prevent leaking filesystem paths, environment variables, or secrets.

    Rules:
    - Strips absolute filesystem paths (/Users/..., /home/..., /tmp/..., etc.)
    - Replaces sensitive keywords (token, secret, key, password)
    """
    if not msg:
        return "An internal tool execution error occurred."

    # Strip absolute path prefixes
    sanitized = re.sub(r"/(?:[a-zA-Z0-9_\.\-]+/)+[a-zA-Z0-9_\.\-]+", "[REDACTED_PATH]", msg)
    # Strip potential secret assignments (e.g. key=xyz, password=xyz)
    sanitized = re.sub(
        r"(?i)(password|secret|token|key|pwd)\s*[=:]\s*['\"]?[^\s,'\"]+",
        r"\1=[REDACTED]",
        sanitized,
    )
    return sanitized.strip()


def run_headless() -> int:
    """Read ToolExecutionDescriptor from stdin, execute via execution registry, and output JSON result."""
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            error_payload = {
                "success": False,
                "output": None,
                "exit_code": 1,
                "error_type": "EmptyInputError",
                "error_message": "No execution descriptor received on stdin.",
            }
            sys.stdout.write(json.dumps(error_payload))
            return 1

        descriptor = ToolExecutionDescriptor.from_json(raw_input)
    except Exception as exc:
        error_payload = {
            "success": False,
            "output": None,
            "exit_code": 1,
            "error_type": "DescriptorParseError",
            "error_message": sanitize_error_message(str(exc)),
        }
        sys.stdout.write(json.dumps(error_payload))
        return 1

    try:
        fn = default_execution_registry.resolve(descriptor.implementation_id)
    except KeyError as exc:
        error_payload = {
            "success": False,
            "output": None,
            "exit_code": 1,
            "error_type": "ImplementationNotFoundError",
            "error_message": sanitize_error_message(str(exc)),
        }
        sys.stdout.write(json.dumps(error_payload))
        return 1

    context: dict[str, Any] = {
        "grant_id": descriptor.grant_id,
        "session_id": descriptor.session_id,
        "agent_id": descriptor.agent_id,
        "request_id": descriptor.request_id,
        "workspace_root": (
            descriptor.filesystem.get("workspace_root") if descriptor.filesystem else None
        ),
        "scratch_dir": descriptor.scratch_dir,
    }

    guard = None
    if descriptor.filesystem is not None:
        from app.runtime.sandbox.filesystem import FilesystemSandboxGuard

        guard = FilesystemSandboxGuard.from_dict(
            descriptor.filesystem,
            scratch_dir=descriptor.scratch_dir,
        )
        guard.install()

    try:
        if guard is not None:
            with guard:
                result = fn(descriptor.parameters, context)
        else:
            result = fn(descriptor.parameters, context)

        success_payload = {
            "success": True,
            "output": result,
            "exit_code": 0,
            "error_type": None,
            "error_message": None,
        }
        sys.stdout.write(json.dumps(success_payload))
        return 0
    except Exception as exc:
        error_payload = {
            "success": False,
            "output": None,
            "exit_code": 1,
            "error_type": exc.__class__.__name__,
            "error_message": sanitize_error_message(str(exc)),
        }
        sys.stdout.write(json.dumps(error_payload))
        return 1


if __name__ == "__main__":
    sys.exit(run_headless())
