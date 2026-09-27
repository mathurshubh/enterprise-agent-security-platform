"""Testing execution handlers — probes for sandbox isolation verification (ADR-032).

These are not production tool implementations. They exist to let the isolation tests
attempt filesystem writes, network connections, environment reads, forks and output
floods from inside the sandbox, and observe that the guards refuse them.

They are deliberately kept out of ``default_execution_registry``. The child runtime's
registry is an explicit packaging boundary: only what it contains can be executed in
the sandbox, so packaging arbitrary filesystem and network primitives there would
defeat the purpose of the boundary. Nothing reachable from a request could resolve
them today — ``implementation_id`` is derived from registered tool objects — but that
holds only while no surface lets a caller influence ``implementation_id``, which a
tool-registration, plugin or MCP surface plausibly would.

Registration is opt-in: ``ProcessToolExecutionSandbox(enable_testing_handlers=True)``
sets ``EASP_SANDBOX_TESTING_HANDLERS`` in the child environment, and only then does
the runner register them.
"""

import os
import time
from collections.abc import Mapping
from typing import Any

from app.runtime.sandbox.registry import SandboxExecutionRegistry


# Built-in test execution handlers for sandbox isolation verification
def _run_test_getpid(_parameters: Mapping[str, Any], _context: Mapping[str, Any]) -> Any:
    return {"pid": os.getpid()}


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


def _run_test_file_op(parameters: Mapping[str, Any], context: Mapping[str, Any]) -> Any:
    """Execute specific filesystem operations to verify sandbox filesystem enforcement."""
    op = parameters.get("op", "open_read")
    path = parameters.get("path")
    mode = parameters.get("mode", "r")
    content = parameters.get("content", "test content")

    if op == "open_read":
        with open(str(path), mode) as f:
            return f.read()

    if op == "open_write":
        write_mode = parameters.get("mode", "w")
        with open(str(path), write_mode) as f:
            f.write(content)
            return len(content)

    if op == "open_append":
        with open(str(path), "a") as f:
            f.write(content)
            return len(content)

    if op == "mkdir":
        os.mkdir(str(path))
        return "created"

    if op == "makedirs":
        os.makedirs(str(path), exist_ok=parameters.get("exist_ok", False))
        return "created_dirs"

    if op == "remove":
        os.remove(str(path))
        return "removed"

    if op == "rmdir":
        os.rmdir(str(path))
        return "removed_dir"

    if op == "rename":
        os.rename(str(parameters["src"]), str(parameters["dst"]))
        return "renamed"

    if op == "replace":
        os.replace(str(parameters["src"]), str(parameters["dst"]))
        return "replaced"

    if op == "symlink":
        os.symlink(str(parameters["src"]), str(parameters["dst"]))
        return "symlinked"

    if op == "chmod":
        os.chmod(str(path), int(parameters.get("mode_int", 0o644)))
        return "chmodded"

    if op == "listdir":
        return os.listdir(str(path))

    if op == "scandir":
        with os.scandir(str(path)) as it:
            return [entry.name for entry in it]

    if op == "scratch_write":
        scratch_dir = context.get("scratch_dir")
        if not scratch_dir:
            raise ValueError("No scratch_dir in context")
        target = os.path.join(scratch_dir, parameters.get("filename", "scratch.txt"))
        with open(target, "w") as f:
            f.write(content)
        return {"target": target, "exists": os.path.exists(target)}

    raise ValueError(f"Unknown test file op: {op}")


def _run_test_network_op(parameters: Mapping[str, Any], _context: Mapping[str, Any]) -> Any:
    """Execute specific network operations to verify sandbox network access enforcement."""
    import socket
    import urllib.request

    op = parameters.get("op", "tcp_connect")
    host = parameters.get("host")
    port = int(parameters.get("port", 80))
    timeout = float(parameters.get("timeout", 2.0))

    if op == "tcp_connect":
        with socket.create_connection((str(host), port), timeout=timeout):
            return "connected"

    if op == "udp_send":
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            data = parameters.get("data", "hello").encode("utf-8")
            s.sendto(data, (str(host), port))
            return "sent"
        finally:
            s.close()

    if op == "http_get":
        url = str(parameters.get("url", f"http://{host}:{port}/"))
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    if op == "unix_connect":
        path = str(parameters.get("path", "/var/run/test.sock"))
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(path)
            return "unix_connected"
        finally:
            s.close()

    if op == "bind_listener":
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((str(host), port))
            return "bound"
        finally:
            s.close()

    raise ValueError(f"Unknown test network op: {op}")


def register_testing_handlers(registry: SandboxExecutionRegistry) -> None:
    """Register the isolation-verification handlers on a child-runtime registry."""
    registry.register("test_getpid", _run_test_getpid)
    registry.register("test_echo", _run_test_echo)
    registry.register("test_sleep", _run_test_sleep)
    registry.register("test_env_dump", _run_test_env_dump)
    registry.register("test_output_flood", _run_test_output_flood)
    registry.register("test_fork_and_persist", _run_test_fork_and_persist)
    registry.register("test_raise_error", _run_test_raise_error)
    registry.register("test_file_op", _run_test_file_op)
    registry.register("test_network_op", _run_test_network_op)
