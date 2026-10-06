"""SqlAgentRepository — durable agent identity and descriptive configuration (ADR-030).

Identity and configuration only. Lifecycle state belongs to the administrative and
enforcement planes (AP.1), and this adapter has no lifecycle responsibility and no
compare-and-set (AP.3): a second version namespace over one agent is the namespace
conflation AP.2 forbids, in another form.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.models.agent import Agent, AgentStatus, RiskTier
from app.repositories.interfaces.agent_repository import AgentRepository
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.session import transactional_session


def _to_domain(row: AgentModel) -> Agent:
    """Reconstruct the domain agent.

    ``status`` is deliberately not read from the row -- there is no such column, and the
    model default (``REGISTERED``, non-executable) stands until ``AgentService`` projects
    the real value from the two planes. A caller that reads this repository directly
    therefore gets a non-executable agent rather than a stale executable one.
    """
    approved = row.approved_tools
    if isinstance(approved, str):
        approved = json.loads(approved)
    return Agent(
        agent_id=row.agent_id,
        name=row.name,
        owner=row.owner,
        risk_tier=RiskTier(row.risk_tier),
        approved_tools=list(approved or []),
    )


class SqlAgentRepository(AgentRepository):
    """Durable adapter for agent identity and descriptive configuration.

    Invariants:
    - No Lifecycle State: ``status`` is neither read nor written. The table has no such
      column (migration 0009).
    - Upsert Semantics: ``save`` creates or replaces descriptive configuration for an
      agent id, matching the in-memory adapter.
    - Fail-Closed Reads: a missing agent returns None rather than a synthesised record.
    """

    def __init__(self, session_factory: sessionmaker[OrmSession] | OrmSession) -> None:
        self._session_factory = session_factory

    def get(self, agent_id: str) -> Agent | None:
        with transactional_session(self._session_factory) as db:
            row = db.get(AgentModel, agent_id)
            return None if row is None else _to_domain(row)

    def save(self, agent: Agent) -> None:
        with transactional_session(self._session_factory) as db:
            row = db.get(AgentModel, agent.agent_id)
            if row is None:
                db.add(
                    AgentModel(
                        agent_id=agent.agent_id,
                        name=agent.name,
                        owner=agent.owner,
                        risk_tier=(
                            agent.risk_tier.value
                            if hasattr(agent.risk_tier, "value")
                            else str(agent.risk_tier)
                        ),
                        approved_tools=list(agent.approved_tools),
                    )
                )
            else:
                row.name = agent.name
                row.owner = agent.owner
                row.risk_tier = (
                    agent.risk_tier.value
                    if hasattr(agent.risk_tier, "value")
                    else str(agent.risk_tier)
                )
                row.approved_tools = list(agent.approved_tools)

    def list(self) -> list[Agent]:
        with transactional_session(self._session_factory) as db:
            rows = db.execute(select(AgentModel).order_by(AgentModel.agent_id)).scalars()
            return [_to_domain(r) for r in rows]


__all__ = ["SqlAgentRepository", "AgentStatus"]
