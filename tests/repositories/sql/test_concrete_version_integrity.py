"""Referential integrity for concrete tool-version identity (Slice 1b).

Two invariants, asymmetric because the domain is:

1. A durable ``ApprovalContinuation`` cannot exist unless its ``(tool_id, tool_version)``
   identifies a registered ``Tool`` version.
2. A durable ``SessionEvent`` is evidence, not a registry reference (ADR-034 §7). It may
   name a family or version that is not registered, and registry changes must neither block
   nor be blocked by it.

Migration 0004 originally held the second invariant the other way: an event's ``tool_id``
had to identify a registered ``ToolFamily``. That premise was that a refused event always
names a registered family. The runtime records the family a request named before and
regardless of its existence, so the constraint made the denial of an unknown tool
unrecordable. Migration 0007 removed both tool references from ``session_events``.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories.sql.base import Base
from app.repositories.sql.engine import create_sql_engine
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.approval_continuation import ApprovalContinuationModel
from app.repositories.sql.models.session import SessionModel
from app.repositories.sql.models.session_event import SessionEventModel
from app.repositories.sql.models.tool import ToolFamilyModel, ToolModel
from app.repositories.sql.session import create_session_factory, transactional_session

NOW = datetime.now(timezone.utc)


@pytest.fixture
def seeded_factory():
    """An agent, a session, and the family ``file_read`` with only version 1.0.0."""
    engine = create_sql_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)

    with transactional_session(factory) as db:
        db.add(
            AgentModel(
                agent_id="agent-1",
                name="agent-1",
                owner="secops@enterprise.internal",
                risk_tier="LOW",
                status="ACTIVE",
                approved_tools=["file_read"],
                created_at=NOW,
                updated_at=NOW,
            )
        )
        db.add(
            SessionModel(
                session_id="sess-1",
                agent_id="agent-1",
                status="ACTIVE",
                next_session_sequence=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        db.add(ToolFamilyModel(tool_id="file_read", created_at=NOW))
        db.add(
            ToolModel(
                tool_id="file_read",
                version="1.0.0",
                governance_enabled=True,
                risk_level="LOW",
                metadata_payload={},
                created_at=NOW,
            )
        )
    return factory


def _grant(**overrides) -> ApprovalContinuationModel:
    fields = {
        "grant_id": "g-1",
        "session_id": "sess-1",
        "agent_id": "agent-1",
        "tool_id": "file_read",
        "tool_version": "1.0.0",
        "execution_parameters": {},
        "originating_audit_event_id": "ae-1",
        "risk_score": 75,
        "required_response": "REQUIRE_APPROVAL",
        "enforcement_epoch": 0,
        "state": "PENDING",
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=15),
    }
    fields.update(overrides)
    return ApprovalContinuationModel(**fields)


def _event(**overrides) -> SessionEventModel:
    fields = {
        "event_id": "evt-1",
        "session_id": "sess-1",
        "agent_id": "agent-1",
        "tool_id": "file_read",
        "tool_version": None,
        "sequence_number": 1,
        "agent_sequence": 1,
        "decision": "DENY",
        "final_decision": None,
        "timestamp": NOW,
        "created_at": NOW,
    }
    fields.update(overrides)
    return SessionEventModel(**fields)


@pytest.mark.security_invariant
def test_invariant_a_durable_grant_must_name_a_registered_tool_version(
    seeded_factory,
) -> None:
    """The version, not merely the family: 2.0.0 is not registered."""
    with pytest.raises(IntegrityError):
        with transactional_session(seeded_factory) as db:
            db.add(_grant(tool_version="2.0.0"))


@pytest.mark.security_invariant
def test_invariant_a_durable_grant_must_name_a_registered_family(
    seeded_factory,
) -> None:
    with pytest.raises(IntegrityError):
        with transactional_session(seeded_factory) as db:
            db.add(_grant(tool_id="never-registered"))


@pytest.mark.security_regression
def test_a_grant_naming_a_registered_version_is_accepted(seeded_factory) -> None:
    """The positive case, so the constraint tests above are not passing vacuously."""
    with transactional_session(seeded_factory) as db:
        db.add(_grant())

    with transactional_session(seeded_factory) as db:
        stored = db.get(ApprovalContinuationModel, "g-1")
        assert stored is not None
        assert (stored.tool_id, stored.tool_version) == ("file_read", "1.0.0")


@pytest.mark.security_invariant
def test_invariant_an_event_naming_an_unregistered_family_is_recorded(seeded_factory) -> None:
    """The denial of a request for a nonexistent tool is evidence and must be storable."""
    with transactional_session(seeded_factory) as db:
        db.add(_event(tool_id="never-registered", tool_version=None))

    with transactional_session(seeded_factory) as db:
        stored = db.get(SessionEventModel, "evt-1")
        assert stored is not None
        assert (stored.tool_id, stored.tool_version) == ("never-registered", None)


@pytest.mark.security_regression
def test_a_refused_event_may_omit_the_version_entirely(seeded_factory) -> None:
    """NULL is a recorded fact: no implementation was ever established."""
    with transactional_session(seeded_factory) as db:
        db.add(_event(tool_version=None))

    with transactional_session(seeded_factory) as db:
        stored = db.get(SessionEventModel, "evt-1")
        assert stored is not None
        assert stored.tool_version is None


@pytest.mark.security_invariant
def test_invariant_an_event_naming_an_unregistered_version_is_recorded(seeded_factory) -> None:
    """A version removed between resolution and the write must not make the event unstorable."""
    with transactional_session(seeded_factory) as db:
        db.add(_event(tool_version="2.0.0"))

    with transactional_session(seeded_factory) as db:
        stored = db.get(SessionEventModel, "evt-1")
        assert stored is not None
        assert (stored.tool_id, stored.tool_version) == ("file_read", "2.0.0")


@pytest.mark.security_invariant
def test_invariant_retained_events_do_not_block_registry_deletion(seeded_factory) -> None:
    """Evidence must not pin registry state: the former ``ON DELETE RESTRICT`` inverted that."""
    with transactional_session(seeded_factory) as db:
        db.add(_event(tool_version="1.0.0"))

    with transactional_session(seeded_factory) as db:
        db.delete(db.get(ToolModel, ("file_read", "1.0.0")))
        db.flush()
        db.delete(db.get(ToolFamilyModel, "file_read"))

    with transactional_session(seeded_factory) as db:
        stored = db.get(SessionEventModel, "evt-1")
        assert stored is not None
        assert (stored.tool_id, stored.tool_version) == ("file_read", "1.0.0")
