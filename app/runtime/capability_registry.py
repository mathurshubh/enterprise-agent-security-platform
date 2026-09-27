"""CapabilityProfileRegistry — Authoritative registry and verification of execution capability profiles (ADR-032)."""

import threading
from collections.abc import Mapping
from typing import Any

from app.models.execution_capability import ExecutionCapabilities
from app.runtime.exceptions import (
    CapabilityDigestMismatchError,
    CapabilityProfileNotFoundError,
)


def verify_capability_binding(
    grant: Any,
    capabilities: ExecutionCapabilities,
    tool_id: str | None = None,
) -> None:
    """Verify that a resolved ExecutionCapabilities instance matches the grant's bound capability contract.

    Invariants (ADR-032):
    1. A grant must carry a capability_profile_id. An unbound grant is refused: a
       capability binding verification that accepts "no binding" verifies nothing.
    2. capability_profile_id must match capabilities.capability_profile_id.
    3. If grant specifies capability_digest, the actual computed SHA-256 digest of
       capabilities must match grant.capability_digest exactly.
    4. Any mismatch fails closed.

    The executor refuses a profile-less grant before reaching here, so this is defense
    in depth for any other caller. Note for ADR-031 approval resumption: a persisted
    ExecutionGrant carrying no capability fields is not executable under this rule,
    which is the intended outcome — it has no capability binding to enforce.

    Raises:
        CapabilityProfileNotFoundError: If the grant carries no capability_profile_id.
        CapabilityDigestMismatchError: If profile_id or computed digest does not match.
    """
    grant_profile_id = getattr(grant, "capability_profile_id", None)
    if grant_profile_id is None:
        raise CapabilityProfileNotFoundError(
            "Grant carries no capability profile binding, so its capabilities cannot "
            "be verified",
            tool_id=tool_id,
        )

    if grant_profile_id != capabilities.capability_profile_id:
        raise CapabilityDigestMismatchError(
            f"Capability profile mismatch: grant bound to '{grant_profile_id}', "
            f"but resolved profile is '{capabilities.capability_profile_id}'",
            expected_digest=grant_profile_id,
            actual_digest=capabilities.capability_profile_id,
            tool_id=tool_id,
        )

    expected_digest = getattr(grant, "capability_digest", None)
    if expected_digest is not None:
        actual_digest = capabilities.compute_digest()
        if actual_digest != expected_digest:
            raise CapabilityDigestMismatchError(
                f"Capability digest mismatch for profile '{capabilities.capability_profile_id}': "
                f"expected digest '{expected_digest}', actual computed digest is '{actual_digest}'",
                expected_digest=expected_digest,
                actual_digest=actual_digest,
                tool_id=tool_id,
            )


class InMemoryCapabilityProfileRegistry:
    """Thread-safe in-memory registry for immutable ExecutionCapabilities profiles."""

    def __init__(
        self,
        initial_profiles: Mapping[str, ExecutionCapabilities] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._profiles: dict[str, ExecutionCapabilities] = {}
        if initial_profiles is not None:
            for profile_id, caps in initial_profiles.items():
                self._profiles[profile_id] = caps

    def register_profile(self, capabilities: ExecutionCapabilities) -> None:
        """Register an immutable ExecutionCapabilities profile."""
        with self._lock:
            self._profiles[capabilities.capability_profile_id] = capabilities

    def resolve_profile(self, profile_id: str) -> ExecutionCapabilities:
        """Resolve an ExecutionCapabilities profile by profile_id.

        Raises:
            CapabilityProfileNotFoundError: If profile_id is not found.
        """
        with self._lock:
            if profile_id not in self._profiles:
                raise CapabilityProfileNotFoundError(
                    f"Capability profile '{profile_id}' is not registered"
                )
            return self._profiles[profile_id]

    def exists(self, profile_id: str) -> bool:
        """Check if a capability profile is registered."""
        with self._lock:
            return profile_id in self._profiles

    def list_profiles(self) -> tuple[ExecutionCapabilities, ...]:
        """List all registered capability profiles."""
        with self._lock:
            return tuple(self._profiles.values())
