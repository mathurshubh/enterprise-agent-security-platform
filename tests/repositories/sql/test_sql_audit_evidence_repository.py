"""Verification and contract tests for SqlAuditEvidenceRepository (Plane 3, ADR-028, ADR-030)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.models.audit_event import AuditEvent, Decision
from app.repositories.interfaces.audit_evidence_repository import (
    AuditEvidenceRepository,
)
from app.repositories.sql.audit_evidence_repository import SqlAuditEvidenceRepository
from app.repositories.sql.base import Base
from app.repositories.sql.engine import create_sql_engine
from app.repositories.sql.session import create_session_factory, transactional_session
from tests.repositories.contracts.base_audit_contract import (
    BaseAuditEvidenceRepositoryContractTests,
)

NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)


def _engine_and_factory():
    engine = create_sql_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, create_session_factory(engine)


class TestSqlAuditEvidenceRepository(BaseAuditEvidenceRepositoryContractTests):
    """Hold the SQL adapter to the same contract as the in-memory one.

    Only the in-memory adapter ran this suite before, which is how the table came to be
    missing ``requested_tool_id`` and ``tool_version`` entirely while declaring ``tool_id``
    NOT NULL against a nullable domain field.
    """

    def create_repository(self) -> AuditEvidenceRepository:
        _engine, factory = _engine_and_factory()
        return SqlAuditEvidenceRepository(factory)


class TestAuditEvidenceIsNotAControlPlaneParticipant:
    """The architectural property, asserted against the schema itself."""

    @pytest.mark.security_invariant
    def test_invariant_audit_events_holds_no_reference_to_the_tool_registry(self) -> None:
        """No FK to ``tools`` or ``tool_families``, by decision.

        A failed audit write denies the request (ADR-030), so a reference to registry state
        would make a missing or deleted registry row deny an unrelated request. The absence
        of these constraints is the contract, so it is asserted rather than assumed.
        """
        engine, _ = _engine_and_factory()

        referred = {
            fk["referred_table"] for fk in inspect(engine).get_foreign_keys("audit_events")
        }

        assert referred == set(), (
            f"audit_events must hold no foreign keys; found references to {referred}. "
            "Audit is historical evidence, not a referential-integrity participant."
        )

    @pytest.mark.security_invariant
    def test_invariant_an_audit_record_may_name_an_unregistered_tool(self) -> None:
        """Nothing registered at all, and the evidence still persists.

        The database is empty of tool families and tool versions. A record naming a tool
        that exists nowhere is precisely what a boundary refusal produces, and it must be
        storable.
        """
        engine, factory = _engine_and_factory()
        repo = SqlAuditEvidenceRepository(factory)

        with transactional_session(factory) as db:
            assert db.execute(text("SELECT COUNT(*) FROM tool_families")).scalar() == 0
            assert db.execute(text("SELECT COUNT(*) FROM tools")).scalar() == 0

        event = AuditEvent(
            event_id="audit-unregistered",
            session_id="session-1",
            agent_id="agent-1",
            requested_tool_id="never_registered_anywhere",
            tool_id="never_registered_anywhere",
            tool_version="9.9.9",
            decision=Decision.DENY,
            timestamp=NOW,
        )

        repo.append(event)

        assert repo.get("audit-unregistered") == event

    @pytest.mark.security_regression
    def test_the_row_level_invariant_is_enforced_by_the_database(self) -> None:
        """A version without a family is rejected — the one permitted constraint class.

        Written through raw SQL because the domain validator refuses this first, and the
        point is that the database refuses it too.
        """
        _engine, factory = _engine_and_factory()

        with pytest.raises(IntegrityError):
            with transactional_session(factory) as db:
                db.execute(
                    text(
                        "INSERT INTO audit_events (event_id, session_id, agent_id,"
                        " requested_tool_id, tool_id, tool_version, decision, timestamp,"
                        " created_at) VALUES ('e-1', 's-1', 'a-1', 'file_read', NULL,"
                        " '1.0.0', 'DENY', :now, :now)"
                    ),
                    {"now": NOW.isoformat()},
                )

    @pytest.mark.security_regression
    def test_principal_is_gone(self) -> None:
        """Schema residue with no domain field, no API exposure and no producer."""
        engine, _ = _engine_and_factory()

        columns = {c["name"] for c in inspect(engine).get_columns("audit_events")}

        assert "principal" not in columns
        assert {"requested_tool_id", "tool_id", "tool_version"} <= columns


class TestSqlAuditQueryOrdering:
    """Pagination has to be stable, which means ties cannot reorder between pages."""

    def test_ties_are_broken_by_event_id_across_pages(self) -> None:
        _engine, factory = _engine_and_factory()
        repo = SqlAuditEvidenceRepository(factory)

        for suffix in ("c", "a", "b"):
            repo.append(
                AuditEvent(
                    event_id=f"evt-{suffix}",
                    session_id="session-1",
                    agent_id="agent-1",
                    requested_tool_id="file_read",
                    tool_id="file_read",
                    decision=Decision.ALLOW,
                    timestamp=NOW,
                )
            )

        first = repo.query(session_id="session-1", limit=2, offset=0)
        second = repo.query(session_id="session-1", limit=2, offset=2)

        assert [e.event_id for e in first] == ["evt-a", "evt-b"]
        assert [e.event_id for e in second] == ["evt-c"]
