"""ExecutionAuthority issuance and verification (ADR-023)."""

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

        assert authority.issue(NOTES, decision) is None
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

        grant = authority.issue(NOTES, Decision.ALLOW)

        assert grant is not None
        assert grant.binding == NOTES
        assert grant.decision == Decision.ALLOW
        assert grant.authority_id == authority.authority_id
        assert grant.issued_at == clock.now
        assert grant.expires_at == clock.now + DEFAULT_GRANT_TTL_SECONDS
        assert authority.outstanding_grant_count == 1

    def test_each_issuance_is_a_distinct_grant(self) -> None:
        authority = ExecutionAuthority()

        first = authority.issue(NOTES, Decision.ALLOW)
        second = authority.issue(NOTES, Decision.ALLOW)

        assert first.grant_id != second.grant_id
        assert first.signature != second.signature

    def test_grant_model_cannot_represent_a_non_allow_decision(self) -> None:
        grant = ExecutionAuthority().issue(NOTES, Decision.ALLOW)

        with pytest.raises(ValidationError):
            ExecutionGrant(**{**grant.model_dump(), "decision": Decision.DENY})

    @pytest.mark.parametrize("ttl", [0, -1.0])
    def test_ttl_must_be_positive(self, ttl) -> None:
        with pytest.raises(ValueError):
            ExecutionAuthority(ttl_seconds=ttl)


class TestVerification:
    def test_exact_match_is_accepted_and_consumed(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW)

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
        grant = authority.issue(authorized, Decision.ALLOW)

        authority.verify_and_consume(grant, requested)

    def test_replayed_grant_is_rejected(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW)
        authority.verify_and_consume(grant, NOTES)

        _refused(
            ExecutionRefusalReason.CONSUMED,
            lambda: authority.verify_and_consume(grant, NOTES),
        )

    def test_different_resource_is_rejected_without_consuming_the_grant(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW)

        _refused(
            ExecutionRefusalReason.RESOURCE_MISMATCH,
            lambda: authority.verify_and_consume(grant, SECRETS),
        )

        authority.verify_and_consume(grant, NOTES)

    def test_different_tool_is_rejected(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW)
        requested = ExecutionBinding.from_operation(
            "directory_list", {"path": "notes.txt"}
        )

        _refused(
            ExecutionRefusalReason.TOOL_MISMATCH,
            lambda: authority.verify_and_consume(grant, requested),
        )

    def test_additional_parameter_is_rejected(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW)
        requested = ExecutionBinding.from_operation(
            "file_read", {"path": "notes.txt", "mode": "raw"}
        )

        _refused(
            ExecutionRefusalReason.PARAMETER_MISMATCH,
            lambda: authority.verify_and_consume(grant, requested),
        )

    def test_tampered_binding_invalidates_the_signature(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW)
        tampered = grant.model_copy(update={"binding": SECRETS})

        _refused(
            ExecutionRefusalReason.INVALID_SIGNATURE,
            lambda: authority.verify_and_consume(tampered, SECRETS),
        )

    def test_extended_expiry_invalidates_the_signature(self) -> None:
        authority = ExecutionAuthority()
        grant = authority.issue(NOTES, Decision.ALLOW)
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
        foreign = ExecutionAuthority().issue(NOTES, Decision.ALLOW)

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
        grant = authority.issue(NOTES, Decision.ALLOW)
        clock.advance(5.0)

        _refused(
            ExecutionRefusalReason.EXPIRED,
            lambda: authority.verify_and_consume(grant, NOTES),
        )

    def test_grant_is_valid_until_it_expires(self) -> None:
        clock = FakeClock()
        authority = ExecutionAuthority(ttl_seconds=5.0, clock=clock)
        grant = authority.issue(NOTES, Decision.ALLOW)
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


class TestBoundedState:
    def test_expired_unconsumed_grants_are_pruned(self) -> None:
        clock = FakeClock()
        authority = ExecutionAuthority(ttl_seconds=5.0, clock=clock)
        for _ in range(3):
            authority.issue(NOTES, Decision.ALLOW)
        assert authority.outstanding_grant_count == 3

        clock.advance(5.0)

        assert authority.outstanding_grant_count == 0
