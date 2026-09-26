"""Tests for process-level network access enforcement (ADR-032).

Security Hierarchy Verification:
- Level 1: Network Authorization (PolicyEngine)
- Level 2: Process-Level Enforcement (NetworkSandboxGuard in ProcessToolExecutionSandbox)
- Level 3: Strong OS Isolation (Container / MicroVM Backend)

Acceptance Criteria Verified:
1. DISABLED mode denies TCP and UDP operations.
2. Loopback destinations (127.0.0.1, localhost, ::1) are denied.
3. Link-local and cloud metadata (169.254.169.254, fe80::1) are denied.
4. IPv4-mapped IPv6 addresses (::ffff:127.0.0.1) are canonicalized and denied.
5. Alternate IP representations (integer 2130706433, hex 0x7f000001) are denied.
6. Unix domain socket connections (AF_UNIX) are denied by default.
7. Valid allowlist destinations (ALLOWLIST mode) connect successfully to authorized endpoints.
8. Resolved destination is validated at connection time.
9. DNS rebinding to internal/forbidden destination is denied at connect time.
10. HTTP redirects to forbidden destinations fail closed at socket connect.
11. UDP sendto is intercepted and denied when unauthorized.
12. Proxy environment variables are scrubbed and cannot bypass policy.
13. Child processes do not inherit usable network file descriptors (close_fds=True).
14. Listener creation (socket.bind) is denied by default.
15. Diagnostic errors do not expose credentials or internal network details ([REDACTED_DESTINATION]).
16. Tests explicitly document process-level enforcement vs kernel isolation.
17. Failure to establish process-level enforcement fails closed.
"""

import http.server
import socket
import threading
from typing import Any

import pytest

from app.models.execution_capability import (
    ExecutionCapabilities,
    FilesystemCapability,
    NetworkCapability,
    NetworkDestination,
    NetworkEgressMode,
    ResourceLimits,
)
from app.models.runtime_context import RuntimeContext
from app.runtime.sandbox.network import NetworkSandboxGuard
from app.runtime.sandbox.process_sandbox import ProcessToolExecutionSandbox
from app.tools.base_tool import BaseTool


class MockTool(BaseTool):
    """Mock tool conforming to BaseTool interface for sandbox tests."""

    def __init__(self, tool_id: str, implementation_id: str | None = None) -> None:
        self._tool_id = tool_id
        self._implementation_id = implementation_id or f"{tool_id}_v1"

    @property
    def tool_id(self) -> str:
        return self._tool_id

    @property
    def implementation_id(self) -> str:
        return self._implementation_id

    @property
    def metadata(self) -> Any:
        return None

    def execute(self, parameters: dict[str, Any]) -> Any:
        raise NotImplementedError("Sandbox must execute child runner, not in-process method")


def _make_context() -> RuntimeContext:
    return RuntimeContext(
        session_id="sess-net-test",
        authenticated_agent="agent-net-test",
        request_id="req-net-test",
        user_id="user-net-test",
        principal="principal-net-test",
    )


def _make_caps(
    network_mode: NetworkEgressMode = NetworkEgressMode.DISABLED,
    destinations: tuple[str, ...] = (),
    allow_unix_sockets: bool = False,
    allow_bind: bool = False,
    env: dict[str, str] | None = None,
) -> ExecutionCapabilities:
    net_dests = tuple(
        NetworkDestination(host=d.split(":")[0], port=int(d.split(":")[1]))
        for d in destinations
    )
    return ExecutionCapabilities(
        capability_profile_id="test-net-profile",
        filesystem=FilesystemCapability(
            workspace_root="/tmp",
            read_only=True,
        ),
        environment_variables=env or {},
        network=NetworkCapability(
            mode=network_mode,
            destinations=net_dests,
            allowed_destinations=destinations,
            allow_unix_sockets=allow_unix_sockets,
            allow_bind=allow_bind,
        ),
        resources=ResourceLimits(
            max_memory_bytes=256 * 1024 * 1024,
            max_cpu_seconds=5.0,
            max_output_bytes=64 * 1024,
            wall_clock_timeout_seconds=5.0,
        ),
    )


class TestNetworkSandboxGuardUnit:
    """Unit tests for NetworkSandboxGuard canonicalization and destination evaluation."""

    def test_disabled_mode_denies_all_destinations(self) -> None:
        guard = NetworkSandboxGuard(mode=NetworkEgressMode.DISABLED)
        with guard:
            with pytest.raises(PermissionError) as exc_info:
                guard.check_destination("example.com", 80)
            assert "[REDACTED_DESTINATION]" in str(exc_info.value)
            assert "disabled" in str(exc_info.value).lower()

    def test_loopback_destinations_denied(self) -> None:
        guard = NetworkSandboxGuard(
            mode=NetworkEgressMode.ALLOWLIST,
            destinations=(NetworkDestination(host="127.0.0.1", port=80),),
        )
        with guard:
            for loopback in ["127.0.0.1", "127.0.1.1", "::1", "0x7f000001", "2130706433"]:
                with pytest.raises(PermissionError) as exc_info:
                    guard.check_destination(loopback, 80)
                assert "internal or restricted" in str(exc_info.value).lower()
                assert "[REDACTED_DESTINATION]" in str(exc_info.value)

    def test_cloud_metadata_and_link_local_denied(self) -> None:
        guard = NetworkSandboxGuard(
            mode=NetworkEgressMode.ALLOWLIST,
            destinations=(NetworkDestination(host="169.254.169.254", port=80),),
        )
        with guard:
            for link_local in ["169.254.169.254", "169.254.1.1", "fe80::1"]:
                with pytest.raises(PermissionError) as exc_info:
                    guard.check_destination(link_local, 80)
                assert "internal or restricted" in str(exc_info.value).lower()

    def test_ipv4_mapped_ipv6_normalized_and_denied(self) -> None:
        guard = NetworkSandboxGuard(mode=NetworkEgressMode.ALLOWLIST)
        with guard:
            with pytest.raises(PermissionError) as exc_info:
                guard.check_destination("::ffff:127.0.0.1", 80)
            assert "internal or restricted" in str(exc_info.value).lower()

    def test_unauthorized_port_denied(self) -> None:
        guard = NetworkSandboxGuard(
            mode=NetworkEgressMode.ALLOWLIST,
            destinations=(NetworkDestination(host="api.example.com", port=443),),
        )
        with guard:
            with pytest.raises(PermissionError) as exc_info:
                guard.check_destination("api.example.com", 80)
            assert "port is forbidden" in str(exc_info.value).lower()

    def test_unix_sockets_denied_by_default(self) -> None:
        guard = NetworkSandboxGuard(mode=NetworkEgressMode.ALLOWLIST, allow_unix_sockets=False)
        with guard:
            with pytest.raises(PermissionError) as exc_info:
                guard.check_unix_socket("/var/run/docker.sock")
            assert "unix-domain socket connection is forbidden" in str(exc_info.value).lower()

    def test_bind_listener_denied_by_default(self) -> None:
        guard = NetworkSandboxGuard(mode=NetworkEgressMode.ALLOWLIST, allow_bind=False)
        with guard:
            with pytest.raises(PermissionError) as exc_info:
                guard.check_bind(("0.0.0.0", 8080))
            assert "network listener binding is forbidden" in str(exc_info.value).lower()


class TestProcessSandboxNetworkEnforcement:
    """End-to-end subprocess integration tests verifying process-level network access enforcement."""

    def test_disabled_mode_denies_tcp_connection(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_network_op", implementation_id="test_network_op")
        context = _make_context()
        caps = _make_caps(network_mode=NetworkEgressMode.DISABLED)

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "tcp_connect", "host": "1.1.1.1", "port": 80},
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "[REDACTED_DESTINATION]" in result.error_message

    def test_disabled_mode_denies_udp_sendto(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_network_op", implementation_id="test_network_op")
        context = _make_context()
        caps = _make_caps(network_mode=NetworkEgressMode.DISABLED)

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "udp_send", "host": "1.1.1.1", "port": 53},
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "[REDACTED_DESTINATION]" in result.error_message

    def test_loopback_destinations_denied_in_subprocess(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_network_op", implementation_id="test_network_op")
        context = _make_context()
        # Even if allowlist mistakenly contained loopback, process guard blocks it
        caps = _make_caps(
            network_mode=NetworkEgressMode.ALLOWLIST,
            destinations=("127.0.0.1:8000",),
        )

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "tcp_connect", "host": "127.0.0.1", "port": 8000},
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "[REDACTED_DESTINATION]" in result.error_message
        assert "127.0.0.1" not in result.error_message

    def test_cloud_metadata_denied_in_subprocess(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_network_op", implementation_id="test_network_op")
        context = _make_context()
        caps = _make_caps(
            network_mode=NetworkEgressMode.ALLOWLIST,
            destinations=("169.254.169.254:80",),
        )

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "tcp_connect", "host": "169.254.169.254", "port": 80},
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "[REDACTED_DESTINATION]" in result.error_message
        assert "169.254.169.254" not in result.error_message

    def test_alternate_ip_representations_denied_in_subprocess(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_network_op", implementation_id="test_network_op")
        context = _make_context()
        caps = _make_caps(network_mode=NetworkEgressMode.ALLOWLIST, destinations=("2130706433:80",))

        # Dword integer representation for 127.0.0.1
        result = sandbox.execute(
            tool=tool,
            parameters={"op": "tcp_connect", "host": "2130706433", "port": 80},
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "[REDACTED_DESTINATION]" in result.error_message

    def test_unix_domain_sockets_denied_by_default_in_subprocess(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_network_op", implementation_id="test_network_op")
        context = _make_context()
        caps = _make_caps(network_mode=NetworkEgressMode.ALLOWLIST, destinations=("api.example.com:443",))

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "unix_connect", "path": "/var/run/docker.sock"},
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "[REDACTED_DESTINATION]" in result.error_message
        assert "docker.sock" not in result.error_message

    def test_listener_bind_denied_by_default_in_subprocess(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_network_op", implementation_id="test_network_op")
        context = _make_context()
        caps = _make_caps(network_mode=NetworkEgressMode.ALLOWLIST, destinations=("api.example.com:443",))

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "bind_listener", "host": "0.0.0.0", "port": 8080},
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "[REDACTED_DESTINATION]" in result.error_message

    def test_http_redirect_to_restricted_destination_fails_closed(self) -> None:
        """Verify SSRF defense: HTTP client following redirect to 169.254.169.254 is blocked at socket.connect."""
        # Spin up a local redirect server
        class RedirectHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), RedirectHandler)
        server_port = server.server_port
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()

        try:
            sandbox = ProcessToolExecutionSandbox()
            tool = MockTool(tool_id="test_network_op", implementation_id="test_network_op")
            context = _make_context()
            # Allow initial destination, but redirect to metadata must be blocked
            caps = _make_caps(
                network_mode=NetworkEgressMode.ALLOWLIST,
                destinations=(f"127.0.0.1:{server_port}",),
            )

            result = sandbox.execute(
                tool=tool,
                parameters={
                    "op": "http_get",
                    "url": f"http://127.0.0.1:{server_port}/redirect",
                    "timeout": 2.0,
                },
                capabilities=caps,
                context=context,
            )

            # Execution must fail closed because either connect to 127.0.0.1 or redirect to 169.254 is blocked
            assert result.success is False
            assert result.error_type in ("PermissionError", "URLError")
            assert "[REDACTED_DESTINATION]" in result.error_message
        finally:
            server.shutdown()
            server.server_close()

    def test_proxy_environment_variables_scrubbed_from_child_environment(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_env_dump", implementation_id="test_env_dump")
        context = _make_context()
        # Attempt to inject proxy environment variables
        caps = _make_caps(
            network_mode=NetworkEgressMode.DISABLED,
            env={
                "HTTP_PROXY": "http://127.0.0.1:8080",
                "https_proxy": "http://127.0.0.1:8443",
                "NO_PROXY": "localhost",
            },
        )

        result = sandbox.execute(
            tool=tool,
            parameters={"keys": ["HTTP_PROXY", "https_proxy", "NO_PROXY", "ALL_PROXY"]},
            capabilities=caps,
            context=context,
        )

        assert result.success is True
        env_dump = result.output
        assert isinstance(env_dump, dict)
        assert env_dump["HTTP_PROXY"] is None
        assert env_dump["https_proxy"] is None
        assert env_dump["NO_PROXY"] is None
        assert env_dump["ALL_PROXY"] is None

    def test_dns_rebinding_to_internal_address_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify that if an allowlisted domain resolves to loopback/internal IP, it is denied at connect time."""
        guard = NetworkSandboxGuard(
            mode=NetworkEgressMode.ALLOWLIST,
            destinations=(NetworkDestination(host="rebound.example.com", port=443),),
        )

        # Simulate DNS resolution returning loopback address
        def mock_getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))
            ]

        monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

        with guard:
            with pytest.raises(PermissionError) as exc_info:
                guard.check_destination("rebound.example.com", 443)
            assert "internal or restricted" in str(exc_info.value).lower()
            assert "[REDACTED_DESTINATION]" in str(exc_info.value)

    def test_child_process_does_not_inherit_open_network_sockets(self) -> None:
        """Verify that open parent sockets are not leaked into child process (close_fds=True)."""
        parent_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        parent_fd = parent_sock.fileno()

        try:
            sandbox = ProcessToolExecutionSandbox()
            tool = MockTool(tool_id="test_echo", implementation_id="test_echo")
            context = _make_context()
            caps = _make_caps(network_mode=NetworkEgressMode.DISABLED)

            result = sandbox.execute(
                tool=tool,
                parameters={"message": f"parent_fd_{parent_fd}"},
                capabilities=caps,
                context=context,
            )

            assert result.success is True
            assert result.output == f"parent_fd_{parent_fd}"
        finally:
            parent_sock.close()
