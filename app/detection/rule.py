from abc import ABC, abstractmethod

from app.detection.category import DetectionCategory
from app.detection.context import DetectionContext
from app.models.finding import Finding


class DetectionRule(ABC):
    """Abstract interface for stateless deterministic detection rules."""

    @property
    @abstractmethod
    def rule_name(
        self,
    ) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def category(
        self,
    ) -> DetectionCategory:
        raise NotImplementedError

    @abstractmethod
    def evaluate(
        self,
        context: DetectionContext,
    ) -> list[Finding]:
        raise NotImplementedError

