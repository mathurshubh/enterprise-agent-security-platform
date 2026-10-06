"""Issuance is closed by either plane and reopened only by the one that closed it.

ADR-024 A.7, ADR-030 AP.8.
"""

import pytest

from app.runtime.execution_authority import ExecutionAuthority, IssuancePlane

AGENT = "agent-1"


@pytest.mark.security_invariant
def test_reinstatement_does_not_reopen_issuance_closed_administratively() -> None:
    """The invariant A.7 exists for, and the reason it belongs in this gate.

    Reinstating an administratively DISABLED agent is permitted: A.5 says it clears the
    suspension and leaves the agent non-executable. With a single issuance flag, the
    enforcement-plane reopen would clear the administrative plane's prohibition too --
    one plane overriding the other.

    Inert before the administrative plane exists, because nothing closes that dimension.
    It stops being inert the moment DISABLED becomes reachable, which is why the contract
    could not wait for the gate after this one.
    """
    authority = ExecutionAuthority()
    authority.suspend_issuance(AGENT, plane=IssuancePlane.ADMINISTRATIVE)
    authority.suspend_issuance(AGENT, plane=IssuancePlane.ENFORCEMENT)

    authority.resume_issuance(AGENT, plane=IssuancePlane.ENFORCEMENT)

    assert authority.issuance_suspended(AGENT) is True
    assert authority.issuance_closed_planes(AGENT) == frozenset(
        {IssuancePlane.ADMINISTRATIVE}
    )


@pytest.mark.security_invariant
def test_neither_plane_can_reopen_the_other() -> None:
    """Symmetric: the administrative plane may not clear a containment either."""
    authority = ExecutionAuthority()
    authority.suspend_issuance(AGENT, plane=IssuancePlane.ENFORCEMENT)

    authority.resume_issuance(AGENT, plane=IssuancePlane.ADMINISTRATIVE)

    assert authority.issuance_suspended(AGENT) is True
    assert authority.issuance_closed_planes(AGENT) == frozenset(
        {IssuancePlane.ENFORCEMENT}
    )


@pytest.mark.security_invariant
def test_issuance_reopens_only_when_every_plane_has_released_it() -> None:
    authority = ExecutionAuthority()
    authority.suspend_issuance(AGENT, plane=IssuancePlane.ADMINISTRATIVE)
    authority.suspend_issuance(AGENT, plane=IssuancePlane.ENFORCEMENT)

    authority.resume_issuance(AGENT, plane=IssuancePlane.ENFORCEMENT)
    assert authority.issuance_suspended(AGENT) is True

    authority.resume_issuance(AGENT, plane=IssuancePlane.ADMINISTRATIVE)
    assert authority.issuance_suspended(AGENT) is False
    assert authority.issuance_closed_planes(AGENT) == frozenset()


def test_the_enforcement_plane_remains_the_default() -> None:
    """Existing callers pass no plane, and must keep meaning containment.

    Checked explicitly because the default is what makes this change inert for the
    callers that exist today; a different default would silently re-target every
    containment already in the codebase.
    """
    authority = ExecutionAuthority()
    authority.suspend_issuance(AGENT)
    assert authority.issuance_closed_planes(AGENT) == frozenset(
        {IssuancePlane.ENFORCEMENT}
    )

    authority.resume_issuance(AGENT)
    assert authority.issuance_suspended(AGENT) is False


def test_closing_the_same_plane_twice_is_idempotent() -> None:
    authority = ExecutionAuthority()
    authority.suspend_issuance(AGENT, plane=IssuancePlane.ENFORCEMENT)
    authority.suspend_issuance(AGENT, plane=IssuancePlane.ENFORCEMENT)

    authority.resume_issuance(AGENT, plane=IssuancePlane.ENFORCEMENT)
    assert authority.issuance_suspended(AGENT) is False


def test_reopening_an_agent_that_was_never_closed_is_harmless() -> None:
    authority = ExecutionAuthority()
    authority.resume_issuance("unknown-agent")
    assert authority.issuance_suspended("unknown-agent") is False


@pytest.mark.security_invariant
def test_every_plane_can_close_issuance() -> None:
    """No plane may be left unable to close issuance.

    Guards the omission: a plane added to the enum without a closing path would be
    unable to withdraw execution authority, which is the failure that matters.
    """
    for plane in IssuancePlane:
        authority = ExecutionAuthority()
        authority.suspend_issuance(AGENT, plane=plane)
        assert authority.issuance_suspended(AGENT) is True
