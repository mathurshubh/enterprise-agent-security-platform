"""ExecutionAuthority — issues and verifies execution grants (ADR-023).

Security invariants
-------------------
1. Only a final ALLOW decision produces a grant. Every other decision yields none.
2. The executor does not trust a caller's claimed binding. It trusts only a grant
   whose authority, signature, expiry and single-use status this authority
   verifies, and the requested operation must exactly match the grant's binding.
3. Every refusal fails closed with ``ExecutionBindingError`` and a reason code, and
   a refused attempt never consumes the grant.

Key material
------------
The signing key is random per process. That is deliberate and differs from the JWT
signing key (finding H-1): grants live only in memory, never cross a process
boundary, and expire within seconds, so a restart should invalidate every
outstanding grant rather than preserve it.
"""

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from enum import Enum
from threading import RLock
from typing import NamedTuple
from uuid import uuid4

from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.models.execution_grant import ExecutionGrant

DEFAULT_GRANT_TTL_SECONDS = 30.0


class _OutstandingGrant(NamedTuple):
    """An issued, unconsumed grant and the agent it was issued for."""

    expires_at: float
    agent_id: str


class ExecutionRefusalReason(str, Enum):
    """Why the execution trust boundary refused an operation."""

    NO_AUTHORITY = "NO_AUTHORITY"
    MISSING_GRANT = "MISSING_GRANT"
    MALFORMED_GRANT = "MALFORMED_GRANT"
    FOREIGN_AUTHORITY = "FOREIGN_AUTHORITY"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"
    REVOKED = "REVOKED"
    TOOL_MISMATCH = "TOOL_MISMATCH"
    RESOURCE_MISMATCH = "RESOURCE_MISMATCH"
    PARAMETER_MISMATCH = "PARAMETER_MISMATCH"
    INVALID_REQUEST = "INVALID_REQUEST"


class ExecutionBindingError(PermissionError):
    """Raised when execution is refused at the execution trust boundary.

    Deliberately distinct from ``ToolExecutionError``: a refusal means the platform
    declined to run the tool, not that the tool failed while running.
    """

    def __init__(
        self,
        reason: ExecutionRefusalReason,
        tool_id: str | None = None,
        detail: str = "",
    ) -> None:
        message = f"Execution refused ({reason.value})"
        if tool_id:
            message += f" for tool '{tool_id}'"
        if detail:
            message += f": {detail}"
        super().__init__(message)
        self.reason = reason
        self.tool_id = tool_id


class ExecutionAuthority:
    """Sole issuer and verifier of execution grants for one process."""

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_GRANT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        self._key = secrets.token_bytes(32)
        self._authority_id = f"authority-{uuid4()}"
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = RLock()
        # Issued, unconsumed, unexpired grants: grant_id -> outstanding record.
        self._outstanding: dict[str, _OutstandingGrant] = {}
        # Grants withdrawn before use: grant_id -> expires_at. Kept until expiry so a
        # revoked grant is refused as REVOKED rather than as an unknown CONSUMED one.
        self._revoked: dict[str, float] = {}
        # Agents whose grant issuance is closed. M2b: a suspended agent must not be
        # able to obtain new authority, including from a request that passed
        # authorization moments before the suspension was written.
        self._issuance_suspended: set[str] = set()

    @property
    def authority_id(self) -> str:
        return self._authority_id

    @property
    def outstanding_grant_count(self) -> int:
        with self._lock:
            self._prune(self._clock())
            return len(self._outstanding)

    def issue(
        self,
        binding: ExecutionBinding,
        decision: Decision,
        *,
        agent_id: str,
    ) -> ExecutionGrant | None:
        """Issue a grant for ``binding`` if and only if it may be authorized.

        Two conditions must hold: ``decision`` is a final ALLOW, and issuance for
        ``agent_id`` is open. Issuance closes when the agent is suspended, so a request
        that passed authorization just before the suspension cannot still obtain
        authority afterwards. Every grant is attributable to an agent; there is no
        unattributed issuance path.
        """
        if decision != Decision.ALLOW:
            return None

        with self._lock:
            if agent_id in self._issuance_suspended:
                return None

            now = self._clock()
            self._prune(now)

            grant_id = f"grant-{uuid4()}"
            expires_at = now + self._ttl_seconds
            signature = self._sign(
                grant_id,
                self._authority_id,
                binding,
                now,
                expires_at,
            )
            self._outstanding[grant_id] = _OutstandingGrant(expires_at, agent_id)

        return ExecutionGrant(
            grant_id=grant_id,
            authority_id=self._authority_id,
            binding=binding,
            issued_at=now,
            expires_at=expires_at,
            signature=signature,
        )

    def verify_and_consume(
        self,
        grant: object,
        requested: ExecutionBinding,
    ) -> None:
        """Verify that ``grant`` authorizes exactly ``requested``, then consume it.

        Raises:
            ExecutionBindingError: for any reason the grant cannot authorize the
                requested operation. A refused attempt does not consume the grant.
        """
        tool_id = requested.tool_id

        if grant is None:
            raise ExecutionBindingError(ExecutionRefusalReason.MISSING_GRANT, tool_id)

        if not isinstance(grant, ExecutionGrant):
            raise ExecutionBindingError(
                ExecutionRefusalReason.MALFORMED_GRANT,
                tool_id,
                "object is not an execution grant",
            )

        if not hmac.compare_digest(
            grant.authority_id.encode("utf-8"),
            self._authority_id.encode("utf-8"),
        ):
            raise ExecutionBindingError(
                ExecutionRefusalReason.FOREIGN_AUTHORITY,
                tool_id,
                "grant was not issued by this execution authority",
            )

        expected_signature = self._sign(
            grant.grant_id,
            grant.authority_id,
            grant.binding,
            grant.issued_at,
            grant.expires_at,
        )
        if not hmac.compare_digest(
            expected_signature.encode("utf-8"),
            grant.signature.encode("utf-8"),
        ):
            raise ExecutionBindingError(
                ExecutionRefusalReason.INVALID_SIGNATURE,
                tool_id,
                "grant signature does not verify",
            )

        with self._lock:
            now = self._clock()

            if now >= grant.expires_at:
                self._outstanding.pop(grant.grant_id, None)
                raise ExecutionBindingError(ExecutionRefusalReason.EXPIRED, tool_id)

            if grant.grant_id in self._revoked:
                raise ExecutionBindingError(
                    ExecutionRefusalReason.REVOKED,
                    tool_id,
                    "grant was revoked before use",
                )

            if grant.grant_id not in self._outstanding:
                raise ExecutionBindingError(
                    ExecutionRefusalReason.CONSUMED,
                    tool_id,
                    "grant has already been used",
                )

            self._require_exact_match(grant.binding, requested)
            del self._outstanding[grant.grant_id]

    def suspend_issuance(self, agent_id: str) -> int:
        """Close grant issuance for an agent and revoke its outstanding grants.

        Both halves happen under one lock, so a concurrent request cannot slip a newly
        issued grant past the revocation: either it is issued before the gate closes and
        is revoked here, or it is refused at issuance.

        Returns:
            The number of outstanding grants revoked.
        """
        with self._lock:
            self._issuance_suspended.add(agent_id)

            revoked = [
                grant_id
                for grant_id, outstanding in self._outstanding.items()
                if outstanding.agent_id == agent_id
            ]
            for grant_id in revoked:
                self._revoked[grant_id] = self._outstanding.pop(grant_id).expires_at

            return len(revoked)

    def resume_issuance(self, agent_id: str) -> None:
        """Reopen grant issuance after an agent is reinstated.

        Grants revoked while the agent was suspended stay revoked: reinstatement
        restores the ability to obtain new authority, not the old authority itself.
        """
        with self._lock:
            self._issuance_suspended.discard(agent_id)

    def issuance_suspended(self, agent_id: str) -> bool:
        """Whether grant issuance is currently closed for an agent."""
        with self._lock:
            return agent_id in self._issuance_suspended

    @staticmethod
    def _require_exact_match(
        authorized: ExecutionBinding,
        requested: ExecutionBinding,
    ) -> None:
        tool_id = requested.tool_id

        if requested.tool_id != authorized.tool_id:
            raise ExecutionBindingError(
                ExecutionRefusalReason.TOOL_MISMATCH,
                tool_id,
                "requested tool differs from the authorized tool",
            )
        if requested.resource != authorized.resource:
            raise ExecutionBindingError(
                ExecutionRefusalReason.RESOURCE_MISMATCH,
                tool_id,
                "requested resource differs from the authorized resource",
            )
        if requested.parameters != authorized.parameters:
            raise ExecutionBindingError(
                ExecutionRefusalReason.PARAMETER_MISMATCH,
                tool_id,
                "requested parameters differ from the authorized parameters",
            )

    def _sign(
        self,
        grant_id: str,
        authority_id: str,
        binding: ExecutionBinding,
        issued_at: float,
        expires_at: float,
    ) -> str:
        payload = json.dumps(
            {
                "authority_id": authority_id,
                "binding": binding.canonical_json(),
                "expires_at": expires_at,
                "grant_id": grant_id,
                "issued_at": issued_at,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hmac.new(
            self._key,
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _prune(self, now: float) -> None:
        expired = [
            grant_id
            for grant_id, outstanding in self._outstanding.items()
            if outstanding.expires_at <= now
        ]
        for grant_id in expired:
            del self._outstanding[grant_id]

        expired_revoked = [
            grant_id
            for grant_id, expires_at in self._revoked.items()
            if expires_at <= now
        ]
        for grant_id in expired_revoked:
            del self._revoked[grant_id]
