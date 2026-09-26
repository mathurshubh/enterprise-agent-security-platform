"""Declarative rule metadata and descriptors for behavioral detection."""

from dataclasses import dataclass

from app.models.session_event import AggregationScope

__all__ = ["DetectionRuleDescriptor"]


@dataclass(frozen=True)
class DetectionRuleDescriptor:
    """Declarative specification of a behavioral detection rule's horizon requirements."""

    name: str
    scope: AggregationScope
    horizon_seconds: float
