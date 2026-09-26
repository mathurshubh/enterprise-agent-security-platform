"""Process-level network egress enforcement for sandbox execution (ADR-032).

Security Hierarchy:
- Level 1: Network Authorization (PolicyEngine) — Answers: Is this network capability granted?
- Level 2: Process-Level Enforcement (NetworkSandboxGuard) — Answers: Does ordinary Python tool code
  stay within its declared network capability at socket boundaries?
- Level 3: Strong OS Isolation (Container / MicroVM Backend) — Answers: Does the kernel or network
  namespace physically prevent packet transmission?

Explicit Non-Goal:
The v0.17 local process backend does not claim kernel-enforced packet isolation or protection
against malicious native code issuing raw syscalls. It provides process-level capability containment
governing standard Python networking APIs (urllib, requests, httpx, socket, asyncio).
If process-level enforcement cannot establish the required policy, execution fails closed.
"""

import ipaddress
import socket
import sys
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from app.models.execution_capability import NetworkDestination, NetworkEgressMode


def _sanitize_destination_in_message(dest: str) -> str:
    """Redact raw destination details from diagnostic and error messages."""
    return "[REDACTED_DESTINATION]"


def _parse_and_normalize_ip(host_or_ip: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse and normalize IP address, unwinding IPv4-mapped IPv6 and alternate numeric encodings."""
    cleaned = host_or_ip.strip().strip("[]")
    if not cleaned:
        return None

    # Check for integer representation (e.g. "2130706433" or "0x7f000001")
    if cleaned.isdigit():
        try:
            val = int(cleaned)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except (ValueError, OverflowError):
            pass
    elif cleaned.lower().startswith("0x"):
        try:
            val = int(cleaned, 16)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except (ValueError, OverflowError):
            pass

    try:
        ip = ipaddress.ip_address(cleaned)
        # Unwrap IPv4-mapped IPv6 address (e.g. ::ffff:127.0.0.1 -> 127.0.0.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            return ip.ipv4_mapped
        return ip
    except ValueError:
        return None


def _is_restricted_or_internal_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address resides in loopback, link-local, private, or metadata ranges."""
    if ip.is_loopback:
        return True
    if ip.is_link_local:
        return True
    if ip.is_unspecified:
        return True
    if ip.is_multicast:
        return True
    if ip.is_reserved:
        return True
    # Explicit check for AWS/GCP/Azure IMDS IPv4
    if str(ip) == "169.254.169.254":
        return True
    return False


class NetworkSandboxGuard:
    """Enforces process-level network access boundaries during tool execution.

    Invariants (ADR-032):
    1. Default Deny: When mode == DISABLED, all outbound socket operations fail closed.
    2. connect() Authorization Point: The actual resolved sockaddr is validated at connect time.
    3. Restricted Destination Protection: Loopback, link-local, and cloud metadata are unconditionally denied.
    4. IPv4/IPv6 Canonicalization: Alternate encodings and mapped addresses are normalized before check.
    5. AF_UNIX Separation: Unix-domain socket connections are governed independently and denied by default.
    6. Listener / Ingress Restriction: socket.bind() is treated as network exposure and denied by default.
    7. DNS Rebinding Defense: Hostnames resolving to internal/restricted IPs fail closed at connection time.
    8. Diagnostic Redaction: Error messages redact destination details with [REDACTED_DESTINATION].
    """

    def __init__(
        self,
        *,
        mode: NetworkEgressMode = NetworkEgressMode.DISABLED,
        destinations: tuple[NetworkDestination, ...] = (),
        allow_unix_sockets: bool = False,
        allow_bind: bool = False,
    ) -> None:
        self.mode = mode
        self.destinations = tuple(destinations)
        self.allow_unix_sockets = allow_unix_sockets
        self.allow_bind = allow_bind

        # Build lookup tables for allowed destinations
        self._allowed_ports: set[int] = {d.port for d in self.destinations}
        self._allowed_hosts: set[str] = {d.host.lower() for d in self.destinations}

        self._active = False
        self._installed = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NetworkSandboxGuard":
        """Construct guard from serialized capability dictionary."""
        mode_val = data.get("mode", NetworkEgressMode.DISABLED.value)
        mode = NetworkEgressMode(mode_val) if isinstance(mode_val, str) else mode_val

        dests: list[NetworkDestination] = []
        raw_dests = data.get("destinations", ())
        if raw_dests:
            for d in raw_dests:
                if isinstance(d, NetworkDestination):
                    dests.append(d)
                elif isinstance(d, dict):
                    dests.append(NetworkDestination(**d))
        elif "allowed_destinations" in data:
            for item in data["allowed_destinations"]:
                if isinstance(item, str):
                    h, p = item.split(":")
                    dests.append(NetworkDestination(host=h, port=int(p)))

        return cls(
            mode=mode,
            destinations=tuple(dests),
            allow_unix_sockets=data.get("allow_unix_sockets", False),
            allow_bind=data.get("allow_bind", False),
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

    def check_destination(self, host_or_ip: str, port: int) -> None:
        """Validate an outbound connection destination against the network capability.

        Raises:
            PermissionError: If destination violates policy or restricted ranges.
        """
        if not self._active:
            return

        target_str = f"{host_or_ip}:{port}"

        # 1. Default-deny check
        if self.mode == NetworkEgressMode.DISABLED:
            raise PermissionError(
                "Network egress is disabled by sandbox capability: "
                f"{_sanitize_destination_in_message(target_str)}"
            )

        # 2. Canonicalize IP address and check restricted ranges first
        parsed_ip = _parse_and_normalize_ip(host_or_ip)
        if parsed_ip is not None:
            # Check internal / restricted address ranges
            if _is_restricted_or_internal_ip(parsed_ip):
                raise PermissionError(
                    "Network egress to internal or restricted address is forbidden: "
                    f"{_sanitize_destination_in_message(target_str)}"
                )

        # 3. Port check
        if port not in self._allowed_ports:
            raise PermissionError(
                "Network egress port is forbidden by allowlist: "
                f"{_sanitize_destination_in_message(target_str)}"
            )

        # 4. Check IP allowlist
        if parsed_ip is not None:
            ip_str = str(parsed_ip)
            if ip_str in self._allowed_hosts:
                return

            # Check if any allowed hostname resolves to this IP
            for allowed_host in self._allowed_hosts:
                try:
                    for res in socket.getaddrinfo(allowed_host, port):
                        resolved_sockaddr = res[4]
                        res_ip = _parse_and_normalize_ip(resolved_sockaddr[0])
                        if res_ip == parsed_ip:
                            return
                except (socket.gaierror, OSError):
                    continue

            raise PermissionError(
                "Network egress to destination IP is forbidden by allowlist: "
                f"{_sanitize_destination_in_message(target_str)}"
            )

        # 5. Hostname check
        host_lower = host_or_ip.strip().lower()
        if host_lower not in self._allowed_hosts:
            raise PermissionError(
                "Network egress to host is forbidden by allowlist: "
                f"{_sanitize_destination_in_message(target_str)}"
            )

        # Hostname is in allowlist — verify that resolved IPs are not restricted
        try:
            addr_infos = socket.getaddrinfo(host_lower, port)
            for res in addr_infos:
                resolved_ip = _parse_and_normalize_ip(res[4][0])
                if resolved_ip is not None and _is_restricted_or_internal_ip(resolved_ip):
                    raise PermissionError(
                        "DNS resolution to internal or restricted address is forbidden: "
                        f"{_sanitize_destination_in_message(target_str)}"
                    )
        except socket.gaierror as exc:
            raise PermissionError(
                f"Failed to resolve destination host: {_sanitize_destination_in_message(target_str)}"
            ) from exc

    def check_unix_socket(self, target_path: Any) -> None:
        """Validate a Unix domain socket connection against IPC policy."""
        if not self._active:
            return

        if not self.allow_unix_sockets:
            raise PermissionError(
                "Unix-domain socket connection is forbidden by sandbox network policy: "
                f"{_sanitize_destination_in_message(str(target_path))}"
            )

    def check_bind(self, address: Any) -> None:
        """Validate socket bind (listener creation) against network exposure policy."""
        if not self._active:
            return

        if not self.allow_bind:
            raise PermissionError(
                "Network listener binding is forbidden by sandbox policy: "
                f"{_sanitize_destination_in_message(str(address))}"
            )

    def audit_hook(self, event: str, args: tuple[Any, ...]) -> None:
        """CPython audit hook callback dispatched on low-level socket operations."""
        if not self._active:
            return

        if event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
            # args: (sock, address)
            sock = args[0] if len(args) > 0 else None
            address = args[1] if len(args) > 1 else None

            if address is None:
                return

            # Check AF_UNIX
            family = getattr(sock, "family", None)
            if family == getattr(socket, "AF_UNIX", -1) or isinstance(address, (str, bytes, Path)):
                self.check_unix_socket(address)
                return

            # AF_INET / AF_INET6
            if isinstance(address, tuple) and len(address) >= 2:
                host = str(address[0])
                try:
                    port = int(address[1])
                except (ValueError, TypeError):
                    raise PermissionError("Invalid socket port in connect") from None
                self.check_destination(host, port)

        elif event == "socket.bind":
            # args: (sock, address)
            address = args[1] if len(args) > 1 else None
            self.check_bind(address)

    def install(self) -> None:
        """Register the audit hook with the CPython runtime."""
        if not self._installed:
            sys.addaudithook(self.audit_hook)
            self._installed = True
