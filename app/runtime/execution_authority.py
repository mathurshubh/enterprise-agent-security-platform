"""ExecutionAuthority — issues and verifies execution grants (ADR-023).

Security invariants
-------------------
1. Only a final ALLOW decision produces a grant. Every other decision yields none.
2. The executor does not trust a caller's claimed binding. It trusts only a grant
   whose authority, signature, expiry and single-use status this authority
   verifies, and the requested operation must exactly match the grant's binding.
3. Every refusal fails closed with ``ExecutionBindingError`` and a reason code, and
   a refused attempt never consumes the grant.
4. Execution identity (``agent_id``, ``session_id``) is fixed at issuance and covered
   by the grant signature. The authority is the sole source of that identity, so no
   downstream component has to trust a caller's claim about who is executing.

Revocation is asymmetric, by decision
-------------------------------------
A grant represents authorized execution **under the governance state observed at
issuance**, subject to immediate revocation by agent containment and bounded by its TTL.

``suspend_issuance`` closes the gate and revokes the agent's outstanding grants in the
same lock hold. Suspension is the containment action the detection pipeline produces, so a
delay there would leave a hole in the enforcement loop. Reinstatement reopens issuance
without restoring revoked grants: it returns the ability to obtain authority, not the
authority itself.

No other governance or configuration change revokes an outstanding grant. Disabling a
tool, unregistering a version, or altering a capability profile takes effect for grants
issued afterwards; grants already issued remain claimable until they expire. That is a
deliberate asymmetry rather than an omission — an operator disabling a tool can tolerate
the TTL, whereas a containment decision cannot — and ``MAX_GRANT_TTL_SECONDS`` is the
compensating bound on it.

Seeing ``suspend_issuance`` revoke grants and concluding that every governance change
should is the mistake this section exists to prevent. Re-checking the governance plane at
claim time would make claiming a second authorization, with the capability and tool
services in its dependency path, and would turn their availability into execution
availability. That is a separate capability, not an extension of this one.

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
from typing import Any, NamedTuple
from uuid import uuid4

from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.models.runtime_execution_grant import RuntimeExecutionGrant
from app.repositories.interfaces.enforcement_state_repository import (
    EnforcementStateRepository,
)

# The grant TTL is a security policy parameter, not an implementation default.
#
# Revocation is deliberately asymmetric (ADR-023). Agent suspension revokes outstanding
# grants immediately, because suspension is the containment action the detection pipeline
# produces and a delay there would leave a hole in the enforcement loop. Every other
# governance or configuration change — a tool disabled, a version unregistered, a
# capability profile altered — takes effect for grants issued afterwards, while grants
# already outstanding stay valid.
#
# So this value is the upper bound on how long such a change can remain ineffective. It is
# the compensating control for that accepted staleness, which is why a ceiling is enforced
# rather than leaving the TTL to a caller: raising it would silently widen the window the
# architecture commits to.
MAX_GRANT_TTL_SECONDS = 30.0
DEFAULT_GRANT_TTL_SECONDS = MAX_GRANT_TTL_SECONDS


class _OutstandingGrant(NamedTuple):
    """An issued, unconsumed grant and the identity it was issued for."""

    expires_at: float
    agent_id: str
    session_id: str


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
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
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


class IssuancePlane(str, Enum):
    """The lifecycle planes that can independently close grant issuance (ADR-024 A.7).

    Issuance is open only when **both** planes permit execution. Tracking one flag per
    agent cannot express that: a single-plane operation reopening the flag would reopen
    issuance while the other plane still forbids execution.
    """

    ADMINISTRATIVE = "ADMINISTRATIVE"
    ENFORCEMENT = "ENFORCEMENT"


class ExecutionAuthority:
    """Sole issuer and verifier of execution grants for one process."""

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_GRANT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        enforcement_repository: EnforcementStateRepository | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if ttl_seconds > MAX_GRANT_TTL_SECONDS:
            # Refused rather than clamped: a caller asking for a longer window has a
            # different security model in mind than the one documented, and silently
            # giving them a shorter one would hide the disagreement.
            raise ValueError(
                f"ttl_seconds must not exceed {MAX_GRANT_TTL_SECONDS}s: the grant TTL "
                "bounds how long a governance change other than agent suspension can "
                "remain ineffective, so raising it widens that window"
            )

        self._key = secrets.token_bytes(32)
        self._authority_id = f"authority-{uuid4()}"
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._enforcement_repository = enforcement_repository
        self._lock = RLock()
        # Issued, unconsumed, unexpired grants: grant_id -> outstanding record.
        self._outstanding: dict[str, _OutstandingGrant] = {}
        # Grants withdrawn before use: grant_id -> expires_at. Kept until expiry so a
        # revoked grant is refused as REVOKED rather than as an unknown CONSUMED one.
        self._revoked: dict[str, float] = {}
        # Agents whose grant issuance is closed, and which plane closed it. M2b: a
        # suspended agent must not be able to obtain new authority, including from a
        # request that passed authorization moments before the suspension was written.
        #
        # Per plane, because issuance is open only when both planes permit execution
        # (ADR-024 A.7). With one flag, reinstating an agent that is also administratively
        # DISABLED would reopen issuance for it -- a single-plane operation overriding the
        # other plane's prohibition. An agent is closed while *any* plane has closed it.
        self._issuance_closed: dict[str, set[IssuancePlane]] = {}

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
        session_id: str,
        expected_epoch: int | None = None,
        capability_profile_id: str | None = None,
        capability_digest: str | None = None,
    ) -> RuntimeExecutionGrant | None:
        """Issue a grant for ``binding`` if and only if it may be authorized.

        ``agent_id`` and ``session_id`` are the authenticated execution identity. They
        are bound into the grant and covered by its signature here, at issuance, so the
        executor never has to trust a caller's claim about who is executing.

        Conditions:
        1. ``decision`` is a final ALLOW.
        2. Issuance for ``agent_id`` is open (not suspended).
        3. CAS epoch check: if ``expected_epoch`` is specified and an enforcement
           repository is present, the persisted epoch must match ``expected_epoch``.
           If a concurrent transition (reinstatement or suspension) advanced the epoch,
           issuance fails closed (returns None).
        """
        if decision != Decision.ALLOW:
            return None

        with self._lock:
            if self._issuance_closed.get(agent_id):
                return None

            if expected_epoch is not None and self._enforcement_repository is not None:
                repo_lock = getattr(self._enforcement_repository, "_lock", None)
                if repo_lock is not None:
                    with repo_lock:
                        persisted_state = self._enforcement_repository.get_state(agent_id)
                        current_epoch = (
                            persisted_state.epoch if persisted_state is not None else 0
                        )
                        if current_epoch != expected_epoch:
                            return None

                        return self._create_grant(
                            binding,
                            agent_id,
                            session_id,
                            capability_profile_id=capability_profile_id,
                            capability_digest=capability_digest,
                        )
                else:
                    persisted_state = self._enforcement_repository.get_state(agent_id)
                    current_epoch = (
                        persisted_state.epoch if persisted_state is not None else 0
                    )
                    if current_epoch != expected_epoch:
                        return None

            return self._create_grant(
                binding,
                agent_id,
                session_id,
                capability_profile_id=capability_profile_id,
                capability_digest=capability_digest,
            )

    def _create_grant(
        self,
        binding: ExecutionBinding,
        agent_id: str,
        session_id: str,
        capability_profile_id: str | None = None,
        capability_digest: str | None = None,
    ) -> RuntimeExecutionGrant:
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
            agent_id=agent_id,
            session_id=session_id,
            capability_profile_id=capability_profile_id,
            capability_digest=capability_digest,
        )
        self._outstanding[grant_id] = _OutstandingGrant(expires_at, agent_id, session_id)

        return RuntimeExecutionGrant(
            grant_id=grant_id,
            authority_id=self._authority_id,
            agent_id=agent_id,
            session_id=session_id,
            binding=binding,
            issued_at=now,
            expires_at=expires_at,
            signature=signature,
            capability_profile_id=capability_profile_id,
            capability_digest=capability_digest,
        )

    def _verify_authenticity(
        self,
        grant: object,
        tool_id: str,
    ) -> RuntimeExecutionGrant:
        """Structural and cryptographic checks, which read no authority state.

        Deliberately lock-free: these depend only on the grant and the signing key, so
        holding the lock across them would widen the critical section without making
        anything more atomic.
        """
        if grant is None:
            raise ExecutionBindingError(ExecutionRefusalReason.MISSING_GRANT, tool_id)

        if not isinstance(grant, RuntimeExecutionGrant):
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
            agent_id=grant.agent_id,
            session_id=grant.session_id,
            capability_profile_id=getattr(grant, "capability_profile_id", None),
            capability_digest=getattr(grant, "capability_digest", None),
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

        return grant

    def _require_claimable_locked(
        self,
        grant: RuntimeExecutionGrant,
        requested: ExecutionBinding,
        tool_id: str,
    ) -> None:
        """Authority-state checks. The caller must already hold ``self._lock``.

        Separated so that validation and the claim itself occur inside a single lock
        hold. A caller that validates, releases the lock, then removes the grant has not
        claimed it: two callers can both observe it outstanding and both proceed.
        """
        now = self._clock()
        self._prune(now)

        if now >= grant.expires_at:
            self._outstanding.pop(grant.grant_id, None)
            raise ExecutionBindingError(ExecutionRefusalReason.EXPIRED, tool_id)

        if grant.grant_id in self._revoked:
            raise ExecutionBindingError(
                ExecutionRefusalReason.REVOKED,
                tool_id,
                "grant was revoked before use",
            )

        outstanding = self._outstanding.get(grant.grant_id)
        if outstanding is None:
            raise ExecutionBindingError(
                ExecutionRefusalReason.CONSUMED,
                tool_id,
                "grant has already been used",
            )

        # The signature already covers identity, so a tampered grant is refused as
        # INVALID_SIGNATURE before reaching here. This cross-check is independent of
        # the signature: it holds the invariant that a grant's identity is the
        # identity this authority issued it for, even if a future code path were to
        # construct a grant outside _create_grant.
        if (
            outstanding.agent_id != grant.agent_id
            or outstanding.session_id != grant.session_id
        ):
            raise ExecutionBindingError(
                ExecutionRefusalReason.IDENTITY_MISMATCH,
                tool_id,
                "grant identity does not match the identity it was issued for",
            )

        self._require_exact_match(grant.binding, requested)

    def verify_grant(
        self,
        grant: object,
        requested: ExecutionBinding,
    ) -> None:
        """Verify that ``grant`` authorizes exactly ``requested`` without consuming it.

        A non-consuming pre-check. It answers "could this grant authorize this
        operation now", which is a strictly weaker statement than "this caller holds
        the right to execute it" — another caller may claim the grant immediately
        afterwards. Only ``claim_grant`` establishes the exclusive right.

        Raises:
            ExecutionBindingError: for any reason the grant cannot authorize the
                requested operation.
        """
        tool_id = requested.tool_id
        checked = self._verify_authenticity(grant, tool_id)
        with self._lock:
            self._require_claimable_locked(checked, requested, tool_id)

    def claim_grant(
        self,
        grant: object,
        requested: ExecutionBinding,
    ) -> None:
        """Atomically verify ``grant`` against ``requested`` and claim it.

        This is the execution trust boundary's single-use gate. Validation and removal
        happen inside one lock hold, so no other caller can observe the grant as
        outstanding between the two: exactly one claim succeeds and every other attempt
        is refused as ``CONSUMED``.

        Verifying and then consuming as separate operations does not achieve this, even
        when both take the lock, because the grant is observable as outstanding in the
        window between them. Nor does removal alone, which is idempotent and therefore
        cannot report whether this caller was the one that claimed it.

        Revocation and suspension serialize against this through the same lock, so a
        grant cannot be claimed after ``suspend_issuance`` has revoked it.

        Raises:
            ExecutionBindingError: for any reason the grant cannot authorize the
                requested operation. A refused attempt never claims the grant.
        """
        tool_id = requested.tool_id
        checked = self._verify_authenticity(grant, tool_id)
        with self._lock:
            self._require_claimable_locked(checked, requested, tool_id)
            del self._outstanding[checked.grant_id]

    def consume_grant(self, grant: RuntimeExecutionGrant) -> None:
        """Remove an outstanding grant without verifying it.

        Not the single-use gate: removal is idempotent, so it cannot distinguish the
        caller that claimed the grant from one that arrived after. ``claim_grant`` is
        the boundary the executor uses; this remains for administrative removal.
        """
        with self._lock:
            if grant.grant_id in self._outstanding:
                del self._outstanding[grant.grant_id]

    def verify_and_consume(
        self,
        grant: object,
        requested: ExecutionBinding,
    ) -> None:
        """Verify that ``grant`` authorizes exactly ``requested``, then claim it.

        Delegates to ``claim_grant``: the two steps its name implies are performed as
        one atomic operation, not sequentially.

        Raises:
            ExecutionBindingError: for any reason the grant cannot authorize the
                requested operation. A refused attempt does not consume the grant.
        """
        self.claim_grant(grant, requested)

    def suspend_issuance(
        self,
        agent_id: str,
        *,
        plane: IssuancePlane = IssuancePlane.ENFORCEMENT,
    ) -> int:
        """Close grant issuance for an agent on one plane, and revoke its grants.

        Both halves happen under one lock, so a concurrent request cannot slip a newly
        issued grant past the revocation: either it is issued before the gate closes and
        is revoked here, or it is refused at issuance.

        ``plane`` defaults to ``ENFORCEMENT`` because containment is the only caller that
        exists today; the administrative plane closes issuance on disablement once that
        transition is reachable.

        Returns:
            The number of outstanding grants revoked.
        """
        with self._lock:
            self._issuance_closed.setdefault(agent_id, set()).add(plane)

            revoked = [
                grant_id
                for grant_id, outstanding in self._outstanding.items()
                if outstanding.agent_id == agent_id
            ]
            for grant_id in revoked:
                self._revoked[grant_id] = self._outstanding.pop(grant_id).expires_at

            return len(revoked)

    def resume_issuance(
        self,
        agent_id: str,
        *,
        plane: IssuancePlane = IssuancePlane.ENFORCEMENT,
    ) -> None:
        """Reopen grant issuance on one plane.

        Clears only the named plane's closure. If another plane still forbids execution,
        issuance stays closed -- no single-plane operation may reopen it while the other
        plane prohibits (ADR-024 A.7). Reinstating an administratively ``DISABLED`` agent
        is the case this exists for: A.5 permits the reinstatement and it clears the
        suspension, but the agent remains non-executable.

        Grants revoked while issuance was closed stay revoked: reopening restores the
        ability to obtain new authority, not the old authority itself.
        """
        with self._lock:
            closed = self._issuance_closed.get(agent_id)
            if closed is None:
                return
            closed.discard(plane)
            if not closed:
                del self._issuance_closed[agent_id]

    def issuance_suspended(self, agent_id: str) -> bool:
        """Whether grant issuance is currently closed for an agent, on any plane."""
        with self._lock:
            return bool(self._issuance_closed.get(agent_id))

    def issuance_closed_planes(self, agent_id: str) -> frozenset[IssuancePlane]:
        """Which planes currently close issuance for an agent.

        Exposed so a caller can tell *why* issuance is closed without inferring it from
        lifecycle state it would have to re-read.
        """
        with self._lock:
            return frozenset(self._issuance_closed.get(agent_id, frozenset()))

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
        # A tool's identity is its id and its version. The signature already covers the
        # version, but that only defeats a forged binding: a genuinely issued grant
        # presented against a different registered version of the same tool would still
        # verify if identity were compared by name alone. Compared here so the grant
        # authorises the implementation it was issued for, not merely the tool's name.
        if requested.tool_version != authorized.tool_version:
            raise ExecutionBindingError(
                ExecutionRefusalReason.TOOL_MISMATCH,
                tool_id,
                "requested tool version differs from the authorized tool version",
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
        *,
        agent_id: str,
        session_id: str,
        capability_profile_id: str | None = None,
        capability_digest: str | None = None,
    ) -> str:
        # Identity is signed unconditionally. Optional capability fields are included
        # only when present, for compatibility with grants that carry no profile; an
        # unsigned identity on a signed token would look authoritative while remaining
        # editable, which is worse than carrying no identity at all.
        payload_dict: dict[str, Any] = {
            "agent_id": agent_id,
            "authority_id": authority_id,
            "binding": binding.canonical_json(),
            "expires_at": expires_at,
            "grant_id": grant_id,
            "issued_at": issued_at,
            "session_id": session_id,
        }
        if capability_profile_id is not None:
            payload_dict["capability_profile_id"] = capability_profile_id
        if capability_digest is not None:
            payload_dict["capability_digest"] = capability_digest

        payload = json.dumps(
            payload_dict,
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
