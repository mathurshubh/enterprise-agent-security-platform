"""Materialized risk posture aggregator service (M5-B).

Owns the collection of per-agent materialized risk projections (AgentRiskAggregate).
Enforces single-ownership, isolation, and fail-closed lifecycle boundaries:
UNINITIALIZED -> HEALTHY / STALE.
"""

from threading import RLock
from typing import Collection, Sequence

from app.models.agent_risk_posture import AgentRiskPosture, PostureState
from app.models.finding import Finding
from app.models.risk_assessment import RiskLevel
from app.models.watermark import BaselineWatermark
from app.services.agent_risk_aggregate import (
    DEFAULT_RULE_VOCABULARY,
    AgentRiskAggregate,
)


class RiskAggregator:
    """Sole owner of in-memory materialized AgentRiskAggregate instances (M5-B).

    Concurrency rules:
    - Service lock (self._lock) protects only the _projections mapping dictionary.
    - Aggregator lock is released before calling any method on AgentRiskAggregate,
      preventing cross-service nested lock contention.
    """

    def __init__(self, rule_vocabulary: Collection[str] | None = None) -> None:
        self._lock = RLock()
        self._projections: dict[str, AgentRiskAggregate] = {}
        self._rule_vocabulary = (
            frozenset(rule_vocabulary)
            if rule_vocabulary is not None
            else DEFAULT_RULE_VOCABULARY
        )

    def get_posture(self, agent_id: str) -> AgentRiskPosture:
        """Retrieve current materialized posture snapshot for an agent.

        Returns a fail-closed UNINITIALIZED posture if no projection exists yet.
        """
        with self._lock:
            aggregate = self._projections.get(agent_id)

        if aggregate is None:
            return AgentRiskPosture(
                agent_id=agent_id,
                state=PostureState.UNINITIALIZED,
                risk_score=0,
                risk_level=RiskLevel.LOW,
                finding_count=0,
                baseline_at=None,
                baseline_sequence=0,
                last_applied_sequence=0,
            )

        return aggregate.snapshot()

    def ingest_finding(self, finding: Finding) -> bool:
        """Incrementally apply an authoritative finding to an agent's projection.

        Returns True if applied, False if duplicate/historical or if no projection exists.
        Lock is released before calling aggregate.apply_finding().
        If an unhandled exception occurs during ingestion, transitions the
        projection to STALE (fail-closed) before re-raising the exception.
        """
        with self._lock:
            aggregate = self._projections.get(finding.agent_id)

        if aggregate is None:
            return False

        try:
            return aggregate.apply_finding(finding)
        except Exception:
            aggregate.mark_stale()
            raise

    def mark_stale(self, agent_id: str) -> None:
        """Transition an agent's projection to STALE (fail-closed)."""
        with self._lock:
            aggregate = self._projections.get(agent_id)

        if aggregate is not None:
            aggregate.mark_stale()

    def reconcile_agent(
        self,
        agent_id: str,
        findings: Sequence[Finding],
        watermark: BaselineWatermark,
    ) -> AgentRiskPosture:
        """Deterministically rebuild an agent's projection from authoritative findings (B-1, B-7).

        Lock is released before calling aggregate.rebuild_from_findings().
        """
        with self._lock:
            aggregate = self._projections.get(agent_id)
            if aggregate is None:
                aggregate = AgentRiskAggregate(watermark, self._rule_vocabulary)
                self._projections[agent_id] = aggregate

        aggregate.rebuild_from_findings(findings, watermark)
        return aggregate.snapshot()

    def reset_to_baseline(self, watermark: BaselineWatermark) -> AgentRiskPosture:
        """Reset projection to a new authoritative enforcement baseline watermark (B-10).

        Lock is released before calling aggregate.reset_to_baseline().
        """
        with self._lock:
            aggregate = self._projections.get(watermark.agent_id)
            if aggregate is None:
                aggregate = AgentRiskAggregate(watermark, self._rule_vocabulary)
                self._projections[watermark.agent_id] = aggregate

        aggregate.reset_to_baseline(watermark)
        return aggregate.snapshot()

    def has_projection(self, agent_id: str) -> bool:
        """Return True if a projection exists for the agent."""
        with self._lock:
            return agent_id in self._projections

    def clear(self) -> None:
        """Clear all stored projections (useful for testing)."""
        with self._lock:
            self._projections.clear()
