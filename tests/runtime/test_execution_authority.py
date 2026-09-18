"""ExecutionAuthority issuance and verification (ADR-023)."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.models.execution_grant import ExecutionGrant
from app.runtime.execution_authority import (
    DEFAULT_GRANT_TTL_SECONDS,
    ExecutionAuthority,
    ExecutionBindingError,
    ExecutionRefusalReason,
)

NOTES = ExecutionBinding.from_operation("file_read", {"path": "notes.txt"})
SECRETS = ExecutionBinding.from_operation("file_read", {"path": "secrets.txt"})


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _refused(reason: ExecutionRefusalReason, action) -> ExecutionBindingError:
    with pytest.raises(ExecutionBindingError) as exc_info:
        action()
    assert exc_info.value.reason is reason
    return exc_info.value


class TestIssuance:
    @pytest.mark.parametrize("decision", [Decision.DENY, Decision.APPROVAL_REQUIRED])
    def test_non_allow_decisions_never_produce_a_grant(self, decision) -> None:
        authority = ExecutionAuthority()

        assert authority.issue(NOTES, decision, agent_id="agent-1") is None
        assert authority.outstanding_grant_count == 0

    def test_every_decision_value_is_classified(self) -> None:
        """Guard: a new Decision member must be classified before it can ship."""
        assert set(Decision) == {
            Decision.ALLOW,
            Decision.DENY,
            Decision.APPROVAL_REQUIRED,
        }

    def test_final_allow_produces_a_grant_bound_to_the_operation(self) -> None:
        clock = FakeClock()
        authority = ExecutionAuthority(clock=clock)

        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")

        assert grant is not None
        assert grant.binding == NOTES
        assert grant.decision == Decision.ALLOW
        assert grant.authority_id == authority.authority_id
        assert grant.issued_at == clock.now
        assert grant.expires_at == clock.now + DEFAULT_GRANT_TTL_SECONDS
        assert authority.outstanding_grant_count == 1

    def test_each_issuance_is_a_distinct_grant(self) -> None:
        authority = ExecutionAuthority()

        first = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        second = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")

        assert first.grant_id != second.grant_id
        assert first.signature != second.signature

    def test_grant_model_cannot_represent_a_non_allow_decision(self) -> None:
        grant = ExecutionAuthority().issue(NOTES, Decision.ALLOW, agent_id="agent-1")

        with pytest.raises(ValidationError):
            ExecutionGrant(**{**grant.model_dump(), "decision": Decision.DENY})

    @pytest.mark.parametrize("ttl", [0, -1.0])
    def test_ttl_must_be_positive(self, ttl) -> None:
        with pytest.raises(ValueError):
            ExecutionAuthority(ttl_seconds=ttl)


class TestVerification:
    def test_exact_match_is_accepted_and_consumed(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")

        authority.verify_and_consume(grant, NOTES)

        assert authority.outstanding_grant_count == 0

    def test_equivalent_parameter_ordering_matches(self) -> None:
        authority = ExecutionAuthority()
        authorized = ExecutionBinding.from_operation(
            "file_read", {"path": "notes.txt", "mode": "r"}
        )
        requested = ExecutionBinding.from_operation(
            "file_read", {"mode": "r", "path": "notes.txt"}
        )
        grant = authority.issue(authorized, Decision.ALLOW, agent_id="agent-1")

        authority.verify_and_consume(grant, requested)

    def test_replayed_grant_is_rejected(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        authority.verify_and_consume(grant, NOTES)

        _refused(
            ExecutionRefusalReason.CONSUMED,
            lambda: authority.verify_and_consume(grant, NOTES),
        )

    def test_different_resource_is_rejected_without_consuming_the_grant(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")

        _refused(
            ExecutionRefusalReason.RESOURCE_MISMATCH,
            lambda: authority.verify_and_consume(grant, SECRETS),
        )

        authority.verify_and_consume(grant, NOTES)

    def test_different_tool_is_rejected(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        requested = ExecutionBinding.from_operation(
            "directory_list", {"path": "notes.txt"}
        )

        _refused(
            ExecutionRefusalReason.TOOL_MISMATCH,
            lambda: authority.verify_and_consume(grant, requested),
        )

    def test_additional_parameter_is_rejected(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        requested = ExecutionBinding.from_operation(
            "file_read", {"path": "notes.txt", "mode": "raw"}
        )

        _refused(
            ExecutionRefusalReason.PARAMETER_MISMATCH,
            lambda: authority.verify_and_consume(grant, requested),
        )

    def test_tampered_binding_invalidates_the_signature(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        tampered = grant.model_copy(update={"binding": SECRETS})

        _refused(
            ExecutionRefusalReason.INVALID_SIGNATURE,
            lambda: authority.verify_and_consume(tampered, SECRETS),
        )

    def test_extended_expiry_invalidates_the_signature(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        extended = grant.model_copy(update={"expires_at": grant.expires_at + 3600})

        _refused(
            ExecutionRefusalReason.INVALID_SIGNATURE,
            lambda: authority.verify_and_consume(extended, NOTES),
        )

    def test_hand_crafted_grant_is_rejected(self) -> None:
        authority = ExecutionAuthority()
        forged = ExecutionGrant(
            grant_id="grant-forged",
            authority_id=authority.authority_id,
            binding=SECRETS,
            issued_at=0.0,
            expires_at=1e12,
            signature="0" * 64,
        )

        _refused(
            ExecutionRefusalReason.INVALID_SIGNATURE,
            lambda: authority.verify_and_consume(forged, SECRETS),
        )

    def test_grant_from_a_foreign_authority_is_rejected(self) -> None:
        authority = ExecutionAuthority()
        foreign = ExecutionAuthority().issue(NOTES, Decision.ALLOW, agent_id="agent-1")

        _refused(
            ExecutionRefusalReason.FOREIGN_AUTHORITY,
            lambda: authority.verify_and_consume(foreign, NOTES),
        )

    def test_non_ascii_authority_identifier_fails_closed(self) -> None:
        authority = ExecutionAuthority()
        forged = ExecutionGrant(
            grant_id="grant-forged",
            authority_id="authoritÿ",
            binding=NOTES,
            issued_at=0.0,
            expires_at=1e12,
            signature="0" * 64,
        )

        _refused(
            ExecutionRefusalReason.FOREIGN_AUTHORITY,
            lambda: authority.verify_and_consume(forged, NOTES),
        )

    def test_expired_grant_is_rejected(self) -> None:
        clock = FakeClock()
        authority = ExecutionAuthority(ttl_seconds=5.0, clock=clock)
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        clock.advance(5.0)

        _refused(
            ExecutionRefusalReason.EXPIRED,
            lambda: authority.verify_and_consume(grant, NOTES),
        )

    def test_grant_is_valid_until_it_expires(self) -> None:
        clock = FakeClock()
        authority = ExecutionAuthority(ttl_seconds=5.0, clock=clock)
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        clock.advance(4.9)

        authority.verify_and_consume(grant, NOTES)

    def test_missing_grant_is_rejected(self) -> None:
        _refused(
            ExecutionRefusalReason.MISSING_GRANT,
            lambda: ExecutionAuthority().verify_and_consume(None, NOTES),
        )

    @pytest.mark.parametrize("not_a_grant", [{"grant_id": "x"}, "grant", object()])
    def test_malformed_grant_is_rejected(self, not_a_grant) -> None:
        _refused(
            ExecutionRefusalReason.MALFORMED_GRANT,
            lambda: ExecutionAuthority().verify_and_consume(not_a_grant, NOTES),
        )

    def test_refusal_is_a_permission_error(self) -> None:
        error = _refused(
            ExecutionRefusalReason.MISSING_GRANT,
            lambda: ExecutionAuthority().verify_and_consume(None, NOTES),
        )

        assert isinstance(error, PermissionError)
        assert error.tool_id == "file_read"


class TestIssuanceGate:
    """Suspension closes issuance and withdraws outstanding authority (M2b).

    Revoking what exists is not enough on its own: a request that passed authorization
    just before the suspension could otherwise obtain a grant immediately afterwards.
    """

    def test_outstanding_grants_are_revoked(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")

        revoked = authority.suspend_issuance("agent-1")

        assert revoked == 1
        error = _refused(
            ExecutionRefusalReason.REVOKED,
            lambda: authority.verify_and_consume(grant, NOTES),
        )
        assert "revoked" in str(error)

    def test_revocation_is_distinguishable_from_consumption(self) -> None:
        authority = ExecutionAuthority()
        consumed = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        authority.verify_and_consume(consumed, NOTES)
        revoked = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        authority.suspend_issuance("agent-1")

        _refused(
            ExecutionRefusalReason.CONSUMED,
            lambda: authority.verify_and_consume(consumed, NOTES),
        )
        _refused(
            ExecutionRefusalReason.REVOKED,
            lambda: authority.verify_and_consume(revoked, NOTES),
        )

    def test_no_new_grant_is_issued_while_issuance_is_closed(self) -> None:
        authority = ExecutionAuthority()
        authority.suspend_issuance("agent-1")

        assert authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1") is None
        assert authority.issuance_suspended("agent-1") is True

    def test_other_agents_keep_their_authority(self) -> None:
        authority = ExecutionAuthority()
        other = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-2")

        authority.suspend_issuance("agent-1")

        assert authority.issuance_suspended("agent-2") is False
        assert authority.issue(SECRETS, Decision.ALLOW, agent_id="agent-2") is not None
        authority.verify_and_consume(other, NOTES)

    def test_suspension_is_idempotent(self) -> None:
        authority = ExecutionAuthority()
        authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")

        assert authority.suspend_issuance("agent-1") == 1
        assert authority.suspend_issuance("agent-1") == 0

    def test_reinstatement_reopens_issuance_without_restoring_old_grants(self) -> None:
        authority = ExecutionAuthority()
        revoked = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        authority.suspend_issuance("agent-1")

        authority.resume_issuance("agent-1")

        assert authority.issuance_suspended("agent-1") is False
        assert authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1") is not None
        # Reinstatement restores the ability to obtain authority, not the old authority.
        _refused(
            ExecutionRefusalReason.REVOKED,
            lambda: authority.verify_and_consume(revoked, NOTES),
        )

    def test_revoked_grants_are_pruned_once_they_expire(self) -> None:
        clock = FakeClock()
        authority = ExecutionAuthority(ttl_seconds=5.0, clock=clock)
        grant = authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        authority.suspend_issuance("agent-1")

        clock.advance(5.0)
        authority.resume_issuance("agent-1")
        authority.issue(SECRETS, Decision.ALLOW, agent_id="agent-1")  # triggers pruning

        _refused(
            ExecutionRefusalReason.EXPIRED,
            lambda: authority.verify_and_consume(grant, NOTES),
        )


class TestConcurrentSuspension:
    def test_a_concurrent_request_cannot_obtain_authority_through_suspension(self) -> None:
        """Whatever the interleaving, no usable grant survives for a suspended agent.

        The adversarial ordering is a request that passes authorization while the agent
        is active and reaches issuance after the suspension has revoked what existed.
        """
        for _ in range(50):
            self._assert_no_usable_grant_survives()

    @staticmethod
    def _assert_no_usable_grant_survives() -> None:
        authority = ExecutionAuthority()

        with ThreadPoolExecutor(max_workers=2) as executor:
            issuing = executor.submit(
                authority.issue, NOTES, Decision.ALLOW, agent_id="agent-1"
            )
            suspending = executor.submit(authority.suspend_issuance, "agent-1")
            grant = issuing.result()
            suspending.result()

        if grant is None:
            # Refused at issuance because the gate had already closed.
            return

        # Issued before the gate closed, so the suspension must have revoked it.
        def consume() -> None:
            authority.verify_and_consume(grant, NOTES)

        _refused(ExecutionRefusalReason.REVOKED, consume)


class TestBoundedState:
    def test_expired_unconsumed_grants_are_pruned(self) -> None:
        clock = FakeClock()
        authority = ExecutionAuthority(ttl_seconds=5.0, clock=clock)
        for _ in range(3):
            authority.issue(NOTES, Decision.ALLOW, agent_id="agent-1")
        assert authority.outstanding_grant_count == 3

        clock.advance(5.0)

        assert authority.outstanding_grant_count == 0
