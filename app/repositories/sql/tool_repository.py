"""SQL implementation of ToolRepository for declarative Tool configuration (Plane 3, ADR-030)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.models.tool import Tool
from app.models.tool_metadata import ToolMetadata
from app.repositories.interfaces.tool_repository import ToolRepository
from app.repositories.sql.models.tool import ToolFamilyModel, ToolModel
from app.repositories.sql.session import transactional_session


class SqlToolRepository(ToolRepository):
    """SQLAlchemy implementation of ToolRepository.

    Invariants:
    - Versioned Identity: keyed by ``(tool_id, version)``. Two versions of one tool are two
      rows; saving one never replaces the other.
    - No Implicit Selection: nothing here resolves a family to a version. There is no
      ``get(tool_id)`` that picks the latest, and ``save`` never updates a "current"
      version. Concrete execution identity is never inferred from family identity
      (F-04/F-05/F-06).
    - Derived Family Anchor: ``save`` materialises the ``tool_families`` row if it is
      absent, because the contract exposes no family-creation operation and a family exists
      exactly when one of its versions does. No API here can create an orphaned family.
    - Canonical Payload: the domain object is reconstructed from ``metadata_payload``
      alone. ``governance_enabled`` and ``risk_level`` are projections written from the same
      source in the same statement, read only for querying, never for reconstruction.
    - Object Isolation: reconstruction parses stored JSON, so returned objects share no
      state with stored rows or with each other.
    - Configuration Only: persists declarative ``ToolMetadata``. Never factory callables,
      ``tool_class`` references or live instance handles.
    - Deterministic Ordering: ``list`` and ``list_versions`` order by ``(tool_id, version)``.
    """

    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    def get(self, tool_id: str, version: str) -> Tool | None:
        with transactional_session(self._session_factory) as db:
            row = db.get(ToolModel, {"tool_id": tool_id, "version": version})
            if row is None:
                return None
            return self._to_domain(row)

    def save(self, tool: Tool) -> None:
        payload = tool.metadata.model_dump(mode="json")
        now = datetime.now(timezone.utc)

        with transactional_session(self._session_factory) as db:
            # The family anchor first: the version row's foreign key requires it, and a
            # version is the only thing that brings a family into existence.
            if db.get(ToolFamilyModel, tool.tool_id) is None:
                db.add(ToolFamilyModel(tool_id=tool.tool_id, created_at=now))
                db.flush()

            existing = db.get(
                ToolModel, {"tool_id": tool.tool_id, "version": tool.version}
            )
            if existing is None:
                db.add(
                    ToolModel(
                        tool_id=tool.tool_id,
                        version=tool.version,
                        governance_enabled=tool.enabled,
                        risk_level=self._risk_projection(tool),
                        metadata_payload=payload,
                        created_at=now,
                    )
                )
                return

            # Replace in place. The projections are rewritten from the same payload in the
            # same statement, so they cannot survive as a description of a previous version
            # of this row.
            existing.metadata_payload = payload
            existing.governance_enabled = tool.enabled
            existing.risk_level = self._risk_projection(tool)

    def list(self) -> list[Tool]:
        with transactional_session(self._session_factory) as db:
            rows = db.execute(
                select(ToolModel).order_by(ToolModel.tool_id, ToolModel.version)
            ).scalars()
            return [self._to_domain(row) for row in rows]

    def list_versions(self, tool_id: str) -> list[Tool]:
        with transactional_session(self._session_factory) as db:
            rows = db.execute(
                select(ToolModel)
                .where(ToolModel.tool_id == tool_id)
                .order_by(ToolModel.version)
            ).scalars()
            return [self._to_domain(row) for row in rows]

    @staticmethod
    def _risk_projection(tool: Tool) -> str:
        """``ToolRiskLevel`` is a str enum, whose ``str()`` is ``'ToolRiskLevel.LOW'``.

        The stored projection has to match the value inside ``metadata_payload``, which
        ``model_dump(mode="json")`` writes as ``'LOW'``.
        """
        risk = tool.risk_level
        return risk.value if hasattr(risk, "value") else str(risk)

    @staticmethod
    def _to_domain(row: ToolModel) -> Tool:
        """Reconstruct from the canonical payload only.

        Deliberately ignores ``governance_enabled`` and ``risk_level``: reading them here
        would make two columns authoritative for one fact and allow a stale projection to
        be returned as domain state.
        """
        return Tool(metadata=ToolMetadata.model_validate(row.metadata_payload))
