"""Durable composition validation (ADR-030 L.6 requirement 1, DB.5 startup check)."""

import pytest

from app.repositories.composition_validation import (
    L6_REFERENCES,
    DurableCompositionError,
    is_durable,
    validate_durable_composition,
)
from app.repositories.factory import create_repositories
from app.repositories.in_memory import (
    InMemoryAgentRepository,
    InMemoryEnforcementStateRepository,
    InMemorySessionRepository,
)
from app.repositories.sql.engine import create_sql_engine


def _sql_container():
    engine = create_sql_engine("sqlite:///:memory:")
    return create_repositories(backend="sql", engine=engine)


@pytest.mark.security_invariant
def test_an_all_volatile_composition_is_valid() -> None:
    """The rule is about *mixing* durability, not about being durable.

    An all-in-memory platform has no durable watermark to point into a volatile allocator,
    so it passes trivially -- which is why the check can be applied unconditionally rather
    than only when a durable backend is configured.
    """
    validate_durable_composition(create_repositories(backend="memory"))


@pytest.mark.security_invariant
def test_a_durable_composition_is_refused_while_findings_are_volatile() -> None:
    """L.6 names this case exactly: durable enforcement with in-memory findings.

    This is the current state of the platform, not a hypothetical. ``FindingsService`` has
    no repository at all, so ``Finding.evidence_sequence`` is unconditionally volatile and
    every durable composition is invalid until the durable findings boundary exists.

    Asserted as a refusal rather than skipped, because the refusal is the deliverable: an
    operator who configures a durable backend today gets a startup failure that names the
    reason, instead of a platform that loses detection after its first restart.
    """
    with pytest.raises(DurableCompositionError) as exc:
        validate_durable_composition(_sql_container())

    message = str(exc.value)
    assert "baseline_evidence_sequence" in message
    assert "Finding.evidence_sequence" in message
    # The remediation is stated, not just the violation.
    assert "durable" in message and "in memory" in message


@pytest.mark.security_invariant
def test_the_refusal_reports_every_violation_not_only_the_first() -> None:
    """An operator fixing a topology needs the whole list.

    Reporting one violation at a time turns a composition problem into a guessing game,
    where each fix reveals the next failure. Driven with a container whose session
    repository is also volatile, so two references are invalid at once.
    """
    container = _sql_container()
    object.__setattr__(container, "session_repository", InMemorySessionRepository())

    with pytest.raises(DurableCompositionError) as exc:
        validate_durable_composition(container)

    message = str(exc.value)
    assert "Finding.evidence_sequence" in message
    assert "SessionEvent.agent_sequence" in message


@pytest.mark.security_invariant
def test_durability_is_decided_by_adapter_identity_not_by_a_claim() -> None:
    """An adapter does not get to declare itself durable.

    Durability is a property of what a repository writes to, so it is read from the
    adapter rather than from an attribute the adapter sets. An unrecognised object is
    treated as volatile: mistaking volatile for durable is the direction that suppresses
    detection, so the conservative reading is the safe one.
    """
    assert is_durable(InMemoryAgentRepository()) is False
    assert is_durable(InMemoryEnforcementStateRepository()) is False
    assert is_durable(object()) is False

    container = _sql_container()
    assert is_durable(container.enforcement_repository) is True
    assert is_durable(container.administrative_repository) is True


@pytest.mark.security_invariant
def test_every_watermark_reference_in_l6_is_checked() -> None:
    """Guards the omission: a reference added to L.6 without a check here is unprotected.

    The state-stamp row is deliberately absent from the table -- it carries no cursor
    semantics, so nothing about it constrains a composition -- and this test asserts the
    table covers the watermark rows rather than asserting a count, so adding a state stamp
    later does not fail it spuriously.
    """
    referenced = {ref.referenced_namespace for ref in L6_REFERENCES}
    assert referenced == {
        "Finding.evidence_sequence",
        "SessionEvent.agent_sequence",
        "AgentEnforcementState.epoch",
    }
    # Every entry must name a referencing store that exists on the container.
    container = create_repositories(backend="memory")
    for ref in L6_REFERENCES:
        assert hasattr(container, ref.referencing_attribute), ref.referencing_attribute
        if ref.referenced_attribute is not None:
            assert hasattr(container, ref.referenced_attribute), ref.referenced_attribute
